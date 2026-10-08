import asyncio
import json

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self):
        self.sent=[]
        self.acked=False

    async def __aenter__(self):
        return self

    async def __aexit__(self,*args):
        return None

    async def send(self,raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if not self.acked:
            self.acked=True
            return json.dumps({"op":"subscribe","success":True})
        raise asyncio.CancelledError


def test_generator_symbols_preserved_and_deduplicated(monkeypatch):
    async def scenario():
        socket=Socket()
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(None).run_batch(
                (symbol for symbol in ["BTCUSDT","BTCUSDT","ETHUSDT"])
            )
        assert socket.sent==[{"op":"subscribe","args":[
            "orderbook.50.BTCUSDT","tickers.BTCUSDT",
            "orderbook.50.ETHUSDT","tickers.ETHUSDT",
        ]}]
    asyncio.run(scenario())


def test_empty_generator_does_not_connect(monkeypatch):
    def fail(*args,**kwargs):
        raise AssertionError("empty generator must not connect")
    monkeypatch.setattr(module.websockets,"connect",fail)
    asyncio.run(module.MicrostructureCollector(None).run_batch(iter(())))
