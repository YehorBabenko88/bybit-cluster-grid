import asyncio
import json

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self):
        self.sent=[]

    async def __aenter__(self):
        return self

    async def __aexit__(self,*args):
        return None

    async def send(self,raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if len(self.sent)==1:
            self.sent.append({"ack":"delivered"})
            return json.dumps({"op":"subscribe","success":True})
        raise asyncio.CancelledError


def test_duplicate_symbols_only_subscribed_once(monkeypatch):
    async def scenario():
        socket=Socket()
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(None).run_batch(["BTCUSDT","BTCUSDT","ETHUSDT","BTCUSDT"])
        subscriptions=[x for x in socket.sent if isinstance(x,dict) and x.get("op")=="subscribe"]
        assert len(subscriptions)==1
        assert subscriptions[0]["args"]==[
            "orderbook.50.BTCUSDT","tickers.BTCUSDT",
            "orderbook.50.ETHUSDT","tickers.ETHUSDT",
        ]
    asyncio.run(scenario())
