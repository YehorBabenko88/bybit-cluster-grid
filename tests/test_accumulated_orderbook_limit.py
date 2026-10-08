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


def test_accumulated_book_levels_reset_and_fresh_snapshot_recovers(monkeypatch):
    async def scenario():
        def frame(kind,seq,u,bids,ts):
            return {"topic":"orderbook.50.BTCUSDT","type":kind,"ts":ts,
                    "data":{"seq":seq,"u":u,"b":bids,"a":[["500","1"]] if kind=="snapshot" else []}}
        initial=frame("snapshot",1,1,[[str(i),"1"] for i in range(100,150)],3000000)
        # Each individual delta is below the 200-level frame limit, but
        # cumulative unique prices exceed the in-memory safety bound.
        deltas=[frame("delta",i+2,i+2,[[str(150+i*50+j),"1"] for j in range(50)],3000100+i*100)
                for i in range(4)]
        recovery=frame("snapshot",7,7,[["100","2"]],3003000)
        socket=Socket([{"op":"subscribe","success":True},initial,*deltas,recovery])
        connections=[]
        def connect(*args,**kwargs):
            connections.append(1)
            return socket
        monkeypatch.setattr(module.websockets,"connect",connect)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        assert len(connections)==1
        books=[e for e in db.events if e[2]=="orderbook_snapshot"]
        assert books[-1][3]["best_bid"]==100.0
        assert len(books)>=2
    asyncio.run(scenario())
