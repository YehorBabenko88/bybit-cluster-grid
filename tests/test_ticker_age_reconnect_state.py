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
            if isinstance(item,Exception):
                raise item
            return json.dumps(item)
        raise asyncio.CancelledError


class DB:
    def __init__(self):
        self.events=[]

    async def insert_event(self, *args):
        self.events.append(args)


def test_reconnect_resets_ticker_delta_state_with_age_filter(monkeypatch):
    async def scenario():
        now=int(time.time()*1000)
        def ticker(ts,values):
            return {"topic":"tickers.BTCUSDT","ts":ts,"data":values}
        first=Socket([
            {"op":"subscribe","success":True},
            ticker(now-1000,{"lastPrice":"100","markPrice":"99"}),
            ConnectionError("socket disconnected"),
        ])
        second=Socket([
            {"op":"subscribe","success":True},
            ticker(now-86400000,{"lastPrice":"999"}),
            ticker(now+1000,{"lastPrice":"101"}),
        ])
        sockets=iter([first,second])
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:next(sockets))
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        monkeypatch.setattr(module,"backoff_delays",lambda:iter([0,0,0]))
        async def no_sleep(_):
            return None
        monkeypatch.setattr(module.asyncio,"sleep",no_sleep)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db,max_ticker_age_ms=300000).run_batch(["BTCUSDT"])
        events=[e for e in db.events if e[2]=="derivatives_ticker"]
        assert len(events)==2
        assert events[0][3]["last_price"]=="100"
        assert events[1][3]["last_price"]=="101"
        assert events[1][3]["mark_price"] is None
    asyncio.run(scenario())
