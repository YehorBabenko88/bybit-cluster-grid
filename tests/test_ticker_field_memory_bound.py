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


def test_unknown_ticker_fields_are_not_merged(monkeypatch):
    async def scenario():
        frame=lambda ts,data: {"topic":"tickers.BTCUSDT","ts":ts,"data":data}
        socket=Socket([
            {"op":"subscribe","success":True},
            frame(3000000,{"lastPrice":"100","extra":"ignore","markPrice":"99"}),
            frame(3002000,{"lastPrice":"101","newExtra":"ignore","markPrice":None}),
        ])
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        db=DB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT"])
        events=[e for e in db.events if e[2]=="derivatives_ticker"]
        assert len(events)==2
        assert events[-1][3]["last_price"]=="101"
        assert events[-1][3]["mark_price"]=="99"
        assert "extra" not in module.TICKER_FIELDS
        assert "newExtra" not in module.TICKER_FIELDS
        assert len(module.TICKER_FIELDS)==15
    asyncio.run(scenario())
