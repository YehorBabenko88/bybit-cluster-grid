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

    async def __aexit__(self,*_):
        self.closed=True

    async def send(self,raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if self.frames:
            return json.dumps(self.frames.pop(0))
        await asyncio.sleep(3600)


class Connections:
    def __init__(self,sockets):
        self.sockets=sockets
        self.count=0

    def __call__(self,*args,**kwargs):
        result=self.sockets[self.count]
        self.count+=1
        return result


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self,*args):
        self.events.append(args)


def test_missing_subscription_ack_times_out_and_retries(monkeypatch):
    async def scenario():
        first=Socket([])
        book={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":3000000,
              "data":{"seq":1,"u":1,"b":[["100","2"]],"a":[["101","3"]]}}
        second=Socket([{"op":"subscribe","success":True},book])
        connections=Connections([first,second])
        monkeypatch.setattr(module.websockets,"connect",connections)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        async def no_delay(_seconds):
            return None
        monkeypatch.setattr(module.asyncio,"sleep",no_delay)
        real_wait_for=asyncio.wait_for
        async def wait_or_timeout(awaitable,timeout):
            if connections.count==1:
                awaitable.close()
                raise asyncio.TimeoutError
            if connections.count==2 and not second.frames:
                awaitable.close()
                raise asyncio.CancelledError
            return await awaitable
        monkeypatch.setattr(module.asyncio,"wait_for",wait_or_timeout)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        assert connections.count==2
        assert first.closed and second.closed
        assert first.sent[0]["args"]==second.sent[0]["args"]
        assert len([e for e in db.events if e[2]=="orderbook_snapshot"])==1
    asyncio.run(scenario())
