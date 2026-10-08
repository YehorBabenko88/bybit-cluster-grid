import asyncio
import json

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self,frames):
        self.frames=list(frames)

    async def __aenter__(self):
        return self

    async def __aexit__(self,*_):
        return None

    async def send(self,raw):
        pass

    async def recv(self):
        if self.frames:
            return json.dumps(self.frames.pop(0))
        raise asyncio.CancelledError


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self,*args):
        self.events.append(args)


@pytest.mark.parametrize("unknown_topic",[
    "tickers.UNEXPECTEDUSDT",
    "orderbook.50.UNEXPECTEDUSDT",
    "orderbook.200.BTCUSDT",
    "tickers.",
])
def test_unsubscribed_market_topic_is_ignored(monkeypatch,unknown_topic):
    async def scenario():
        unknown={"topic":unknown_topic,"type":"snapshot","ts":3000000,
                 "data":{"seq":1,"u":1,"b":[["999","2"]],"a":[["1000","3"]],
                         "lastPrice":"999"}}
        valid={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":3000000,
               "data":{"seq":1,"u":1,"b":[["100","2"]],"a":[["101","3"]]}}
        socket=Socket([{"op":"subscribe","success":True},unknown,valid])
        connects=[]
        def connect(*args,**kwargs):
            connects.append(1)
            return socket
        monkeypatch.setattr(module.websockets,"connect",connect)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        assert len(connects)==1
        assert len(db.events)==1
        assert db.events[0][0]=="BTCUSDT"
        assert db.events[0][3]["best_bid"]==100.0
    asyncio.run(scenario())
