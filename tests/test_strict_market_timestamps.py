import asyncio
import json

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


@pytest.mark.parametrize("bad_ts",[True,False,0,-1,1.5,"1.5","0","-1"," 123 ", "9"*5000])
def test_bad_timestamp_does_not_poison_ticker_state(monkeypatch,bad_ts):
    async def scenario():
        def ticker(ts,price):
            return {"topic":"tickers.BTCUSDT","ts":ts,"data":{"lastPrice":price}}
        socket=Socket([
            {"op":"subscribe","success":True},
            ticker(bad_ts,"999"),
            ticker(3000000,"100"),
        ])
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        events=[e for e in db.events if e[2]=="derivatives_ticker"]
        assert len(events)==1
        assert events[0][3]["last_price"]=="100"
    asyncio.run(scenario())
