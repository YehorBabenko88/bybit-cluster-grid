"""Malformed active instrument records must not become false delistings."""
import asyncio
import pytest
from grid.bybit import linear_symbols


class Response:
    status=200
    headers={}
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    def raise_for_status(self):pass
    async def json(self,**kwargs):
        return {"retCode":0,"result":{"list":[
            {"status":"Trading","contractType":"LinearPerpetual","symbol":"BTCUSDT",
             "priceFilter":{"tickSize":"0.1"}},
            {"status":"Trading","contractType":"LinearPerpetual","symbol":"ETHUSDT",
             "priceFilter":{}},
        ],"nextPageCursor":""}}


class Session:
    def __init__(self,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    def get(self,*args,**kwargs):return Response()


def test_malformed_active_instrument_fails_entire_snapshot(monkeypatch):
    monkeypatch.setattr("grid.bybit.aiohttp.ClientSession",Session)
    with pytest.raises(RuntimeError,match="malformed instrument"):
        asyncio.run(linear_symbols("https://example.invalid",max_attempts=1))
