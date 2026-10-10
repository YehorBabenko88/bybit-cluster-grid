import asyncio

import pytest

from grid import bybit


class FakeResponse:
    def __init__(self,status,payload,headers=None):
        self.status=status
        self.payload=payload
        self.headers=headers or {}
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False
    def raise_for_status(self):
        if self.status>=400:
            import aiohttp
            raise aiohttp.ClientResponseError(None,(),status=self.status)
    async def json(self,content_type=None):
        return self.payload


class FakeSession:
    responses=[]
    def __init__(self,*args,**kwargs):
        self.items=list(self.responses)
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False
    def get(self,*args,**kwargs):
        return self.items.pop(0)


def test_linear_symbols_retries_rate_limit_and_deduplicates(monkeypatch):
    async def run():
        good={"retCode":0,"result":{"list":[
            {"symbol":"BTCUSDT","status":"Trading","contractType":"LinearPerpetual",
             "priceFilter":{"tickSize":"0.1"},"settleCoin":"USDT"},
            {"symbol":"BTCUSDT","status":"Trading","contractType":"LinearPerpetual",
             "priceFilter":{"tickSize":"0.1"},"settleCoin":"USDT"},
        ],"nextPageCursor":""}}
        FakeSession.responses=[FakeResponse(429,{},{"Retry-After":"0"}),FakeResponse(200,good)]
        monkeypatch.setattr(bybit.aiohttp,"ClientSession",FakeSession)
        monkeypatch.setattr(bybit.random,"uniform",lambda *a:0)
        rows=await bybit.linear_symbols("https://example.invalid",max_attempts=2)
        assert [x["symbol"] for x in rows]==["BTCUSDT"]
    asyncio.run(run())


def test_linear_symbols_rejects_cursor_loop(monkeypatch):
    async def run():
        page={"retCode":0,"result":{"list":[],"nextPageCursor":"same"}}
        FakeSession.responses=[FakeResponse(200,page),FakeResponse(200,page)]
        monkeypatch.setattr(bybit.aiohttp,"ClientSession",FakeSession)
        with pytest.raises(RuntimeError,match="cursor loop"):
            await bybit.linear_symbols("https://example.invalid",max_attempts=1)
    asyncio.run(run())


def test_linear_symbols_fails_closed_on_exchange_error(monkeypatch):
    async def run():
        FakeSession.responses=[FakeResponse(200,{"retCode":10006,"retMsg":"rate limit","result":{}})]
        monkeypatch.setattr(bybit.aiohttp,"ClientSession",FakeSession)
        with pytest.raises(RuntimeError,match="10006"):
            await bybit.linear_symbols("https://example.invalid",max_attempts=1)
    asyncio.run(run())


def test_reachability_probe_always_closes_socket(monkeypatch):
    from grid import resilience
    class FakeSocket:
        def __init__(self): self.closed=False
        def close(self): self.closed=True
    sock=FakeSocket()
    monkeypatch.setattr(resilience.socket,"create_connection",lambda *a,**k:sock)
    assert resilience._probe_tcp("example.invalid",443,3) is True
    assert sock.closed is True

@pytest.mark.parametrize('tick', ['NaN', 'Infinity', '-Infinity'])
def test_linear_symbols_rejects_nonfinite_tick(monkeypatch, tick):
    row={'symbol':'BTCUSDT','status':'Trading','contractType':'LinearPerpetual',
         'priceFilter':{'tickSize':tick}}
    FakeSession.responses=[FakeResponse(200,{'retCode':0,'result':{'list':[row]}})]
    monkeypatch.setattr(bybit.aiohttp,'ClientSession',FakeSession)
    with pytest.raises(RuntimeError,match='malformed instrument'):
        asyncio.run(bybit.linear_symbols('https://example.invalid',max_attempts=1))

@pytest.mark.parametrize('header',['NaN','Infinity','-5','99999999'])
def test_linear_symbols_bounds_retry_after(monkeypatch,header):
    row={'symbol':'BTCUSDT','status':'Trading','contractType':'LinearPerpetual',
         'priceFilter':{'tickSize':'0.1'}}
    FakeSession.responses=[FakeResponse(429,{}, {'Retry-After':header}),
                          FakeResponse(200,{'retCode':0,'result':{'list':[row]}})]
    monkeypatch.setattr(bybit.aiohttp,'ClientSession',FakeSession)
    monkeypatch.setattr(bybit.random,'uniform',lambda *a:0)
    delays=[]
    async def sleep(delay): delays.append(delay)
    monkeypatch.setattr(bybit.asyncio,'sleep',sleep)
    asyncio.run(bybit.linear_symbols('https://example.invalid',max_attempts=2))
    assert len(delays)==1
    assert 0<=delays[0]<=30
