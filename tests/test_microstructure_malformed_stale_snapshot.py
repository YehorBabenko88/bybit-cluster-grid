import asyncio
import json
import time

import pytest

from grid import microstructure as module


class RecordingDB:
    def __init__(self):
        self.events=[]

    async def insert_event(self,symbol,ts,kind,payload):
        self.events.append((symbol,kind,payload))


class Socket:
    def __init__(self,frames):
        self.frames=iter(frames)
        self.sent=[]

    async def __aenter__(self):
        return self

    async def __aexit__(self,*args):
        return None

    async def send(self,raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        try:
            return next(self.frames)
        except StopIteration:
            raise asyncio.CancelledError


def test_malformed_stale_snapshot_does_not_clear_valid_book(monkeypatch):
    async def scenario():
        now=int(time.time()*1000)
        def frame(seq,u,kind,bids,asks,ts):
            return json.dumps({"topic":"orderbook.50.BTCUSDT","type":kind,
                "ts":ts,"data":{"seq":seq,"u":u,"b":bids,"a":asks}})
        socket=Socket([
            json.dumps({"op":"subscribe","success":True}),
            frame(100,10,"snapshot",[["100","2"]],[["101","3"]],now),
            frame(90,9,"snapshot",[["bad","quantity"]],[["101","3"]],now+1000),
            frame(101,11,"delta",[["100","4"]],[],now+2000),
        ])
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        db=RecordingDB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        snapshots=[payload for _,kind,payload in db.events if kind=="orderbook_snapshot"]
        assert len(snapshots)==2
        assert snapshots[-1]["sequence"]==101
        assert snapshots[-1]["update_id"]==11
        assert snapshots[-1]["bid_volume"]==4.0
    asyncio.run(scenario())
