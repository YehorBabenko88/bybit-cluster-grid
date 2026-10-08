import asyncio
import json
import time

import pytest

from grid import microstructure as module


class RecordingDB:
    def __init__(self):
        self.events=[]

    async def insert_event(self,symbol,ts,kind,payload):
        self.events.append((symbol,ts,kind,payload))


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


@pytest.mark.parametrize("bad_data",[{},{"unknown":"100"},{"lastPrice":None}])
def test_empty_ticker_delta_does_not_advance_timestamp(monkeypatch,bad_data):
    async def scenario():
        now=int(time.time()*1000)
        def frame(ts,data):
            return json.dumps({"topic":"tickers.BTCUSDT","ts":ts,"data":data})
        socket=Socket([
            json.dumps({"op":"subscribe","success":True}),
            frame(now+3000,bad_data),
            frame(now+1000,{"lastPrice":"100"}),
            frame(now+2000,{"lastPrice":"101"}),
        ])
        async def ready():
            return None
        monkeypatch.setattr(module,"wait_for_internet",ready)
        monkeypatch.setattr(module.websockets,"connect",lambda *a,**kw:socket)
        db=RecordingDB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db,snapshot_ms=1000).run_batch(["BTCUSDT"])
        tickers=[(ts,p) for _,ts,kind,p in db.events if kind=="derivatives_ticker"]
        assert [ts for ts,_ in tickers]==[now+1000,now+2000]
        assert [p["last_price"] for _,p in tickers]==["100","101"]
    asyncio.run(scenario())
