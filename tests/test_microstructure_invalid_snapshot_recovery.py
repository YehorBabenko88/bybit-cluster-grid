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

    async def __aenter__(self):
        return self

    async def __aexit__(self,*args):
        return None

    async def send(self,raw):
        pass

    async def recv(self):
        try:
            return next(self.frames)
        except StopIteration:
            raise asyncio.CancelledError


@pytest.mark.parametrize("bad_seq,bad_update",[(None,11),(101,None),(True,11),(101,False),(-1,11),(101,-1)])
def test_invalid_snapshot_metadata_requires_recovery(monkeypatch,bad_seq,bad_update):
    async def scenario():
        now=int(time.time()*1000)
        def frame(seq,u,kind,bids,asks,ts):
            return json.dumps({"topic":"orderbook.50.BTCUSDT","type":kind,
                "ts":ts,"data":{"seq":seq,"u":u,"b":bids,"a":asks}})
        socket=Socket([
            json.dumps({"op":"subscribe","success":True}),
            frame(100,10,"snapshot",[["100","2"]],[["101","3"]],now),
            frame(bad_seq,bad_update,"snapshot",[["100","99"]],[["101","99"]],now+1000),
            frame(102,12,"delta",[["100","88"]],[],now+2000),
            frame(103,13,"snapshot",[["100","5"]],[["101","6"]],now+3000),
            frame(104,14,"delta",[["100","7"]],[],now+4000),
        ])
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        db=RecordingDB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        snapshots=[payload for _,kind,payload in db.events if kind=="orderbook_snapshot"]
        assert len(snapshots)==3
        assert [p["sequence"] for p in snapshots]==[100,103,104]
        assert snapshots[-1]["bid_depth"]==7.0
        assert snapshots[-1]["ask_depth"]==6.0
    asyncio.run(scenario())
