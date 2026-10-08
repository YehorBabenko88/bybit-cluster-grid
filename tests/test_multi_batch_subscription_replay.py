import asyncio
import json

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self, frames):
        self.frames=list(frames)
        self.sent=[]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if self.frames:
            return json.dumps(self.frames.pop(0))
        raise asyncio.CancelledError


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self, *args):
        self.events.append(args)


def test_early_snapshot_replayed_after_second_subscription_ack(monkeypatch):
    async def scenario():
        symbols=[f"COIN{i}USDT" for i in range(11)]
        first_topics=[item for sym in symbols[:10] for item in
                      (f"orderbook.50.{sym}",f"tickers.{sym}")]
        last_topics=[f"orderbook.50.{symbols[10]}",f"tickers.{symbols[10]}"]
        early={"topic":f"orderbook.50.{symbols[0]}","type":"snapshot","ts":3000000,
               "data":{"seq":1,"u":1,"b":[["100","2"]],"a":[["101","3"]]}}
        socket=Socket([
            {"op":"subscribe","success":True,"data":{"args":first_topics}},
            early,
            {"op":"subscribe","success":True,"data":{"args":last_topics}},
        ])
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**k:socket)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(symbols)
        assert len(socket.sent)==2
        books=[e for e in db.events if e[2]=="orderbook_snapshot"]
        assert len(books)==1
        assert books[0][0]==symbols[0]
        assert books[0][3]["best_bid"]==100.0
        assert books[0][3]["best_ask"]==101.0
    asyncio.run(scenario())
