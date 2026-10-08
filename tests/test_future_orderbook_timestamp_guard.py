import asyncio
import json
import time

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self, frames):
        self.frames=list(frames)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def send(self, raw):
        return None

    async def recv(self):
        if self.frames:
            return json.dumps(self.frames.pop(0))
        raise asyncio.CancelledError


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self, *args):
        self.events.append(args)


def test_future_orderbook_snapshot_does_not_poison_sequence(monkeypatch):
    async def scenario():
        now=int(time.time()*1000)
        def snapshot(ts,seq,bid):
            return {"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":ts,
                    "data":{"seq":seq,"u":seq,"b":[[str(bid),"2"]],"a":[["200","3"]]}}
        socket=Socket([
            {"op":"subscribe","success":True},
            snapshot(now+86400000,999,999),
            snapshot(now,1,100),
        ])
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        books=[e for e in db.events if e[2]=="orderbook_snapshot"]
        assert len(books)==1
        assert books[0][3]["best_bid"]==100.0
    asyncio.run(scenario())
