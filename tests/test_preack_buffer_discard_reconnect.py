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
            item=self.frames.pop(0)
            if isinstance(item,BaseException):
                raise item
            return json.dumps(item)
        raise asyncio.CancelledError


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self,*args):
        self.events.append(args)


def test_preack_buffer_discarded_when_subscription_fails(monkeypatch):
    async def scenario():
        now=int(time.time()*1000)
        def ticker(price):
            return {"topic":"tickers.BTCUSDT","ts":now,"data":{"lastPrice":price}}
        first=Socket([
            ticker("999"),
            {"op":"subscribe","success":False,"ret_msg":"rejected"},
        ])
        second=Socket([
            {"op":"subscribe","success":True},
            ticker("100"),
        ])
        sockets=iter([first,second])
        connections=[]
        def connect(*a,**kw):
            socket=next(sockets)
            connections.append(socket)
            return socket
        monkeypatch.setattr(module.websockets,"connect",connect)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        monkeypatch.setattr(module,"backoff_delays",lambda:iter([0,0,0]))
        async def no_sleep(_):
            return None
        monkeypatch.setattr(module.asyncio,"sleep",no_sleep)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        events=[e for e in db.events if e[2]=="derivatives_ticker"]
        assert len(connections)==2
        assert len(events)==1
        assert events[0][3]["last_price"]=="100"
    asyncio.run(scenario())
