import asyncio
import json

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self, frames):
        self.frames=list(frames)
        self.sent=[]
        self.closed=False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed=True

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if self.frames:
            return json.dumps(self.frames.pop(0))
        raise asyncio.CancelledError


class Connections:
    def __init__(self, sockets):
        self.sockets=sockets
        self.count=0

    def __call__(self,*args,**kwargs):
        socket=self.sockets[self.count]
        self.count+=1
        return socket


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self,*args):
        self.events.append(args)


def test_rejected_subscription_reconnects_and_retries(monkeypatch):
    async def scenario():
        rejected=Socket([{"op":"subscribe","success":False,"ret_msg":"rate limit"}])
        snapshot={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":3000000,
                  "data":{"seq":1,"u":1,"b":[["100","2"]],"a":[["101","3"]]}}
        accepted=Socket([{"op":"subscribe","success":True},snapshot])
        connections=Connections([rejected,accepted])
        monkeypatch.setattr(module.websockets,"connect",connections)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        async def no_delay(_seconds):
            return None
        monkeypatch.setattr(module.asyncio,"sleep",no_delay)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        assert connections.count==2
        assert rejected.closed
        assert accepted.closed
        assert rejected.sent[0]["op"]=="subscribe"
        assert accepted.sent[0]["args"]==rejected.sent[0]["args"]
        books=[e for e in db.events if e[2]=="orderbook_snapshot"]
        assert len(books)==1
        assert books[0][3]["best_bid"]==100.0
    asyncio.run(scenario())
