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
            return self.frames.pop(0)
        raise asyncio.CancelledError


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self,*args):
        self.events.append(args)


@pytest.mark.parametrize("bad_raw",["{invalid","",b"\\xff"])
def test_invalid_market_json_keeps_socket_and_next_snapshot(monkeypatch,bad_raw):
    async def scenario():
        good={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":3000000,
              "data":{"seq":1,"u":1,"b":[["100","2"]],"a":[["101","3"]]}}
        socket=Socket([json.dumps({"op":"subscribe","success":True}),bad_raw,json.dumps(good)])
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
        books=[event for event in db.events if event[2]=="orderbook_snapshot"]
        assert len(books)==1
        assert books[0][3]["best_bid"]==100.0
    asyncio.run(scenario())
