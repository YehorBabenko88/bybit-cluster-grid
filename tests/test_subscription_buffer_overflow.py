import asyncio
import json

import pytest

from grid import microstructure as module


class Socket:
    def __init__(self, frames):
        self.frames=iter(frames)
        self.sent=[]
        self.closed=False

    async def __aenter__(self):
        return self

    async def __aexit__(self,*_):
        self.closed=True

    async def send(self,raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        return json.dumps(next(self.frames))


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


def test_early_market_frame_buffer_overflow_reconnects(monkeypatch):
    async def scenario():
        flood={"topic":"tickers.BTCUSDT","ts":3000000,
               "data":{"lastPrice":"100"}}
        # A non-ACK market-data flood must never grow the buffer unboundedly.
        first=Socket([flood]*2001)
        snapshot={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":3000000,
                  "data":{"seq":1,"u":1,"b":[["100","2"]],"a":[["101","3"]]}}
        second=Socket([{"op":"subscribe","success":True},snapshot])
        connections=Connections([first,second])
        monkeypatch.setattr(module.websockets,"connect",connections)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        async def no_delay(_seconds):
            return None
        monkeypatch.setattr(module.asyncio,"sleep",no_delay)
        original_recv=second.recv
        async def second_recv():
            try:
                return await original_recv()
            except StopIteration:
                raise asyncio.CancelledError
        second.recv=second_recv
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        assert connections.count==2
        assert first.closed and second.closed
        assert first.sent[0]["args"]==second.sent[0]["args"]
        books=[event for event in db.events if event[2]=="orderbook_snapshot"]
        assert len(books)==1
        assert books[0][3]["best_bid"]==100.0
    asyncio.run(scenario())
