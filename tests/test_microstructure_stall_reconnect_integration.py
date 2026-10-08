import asyncio
import json

import pytest

from grid import microstructure as module


class FakeSocket:
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
        await asyncio.sleep(3600)


class FakeConnections:
    def __init__(self, sockets):
        self.sockets=sockets
        self.opened=0

    def __call__(self, *args, **kwargs):
        sock=self.sockets[self.opened]
        self.opened+=1
        return sock


class FakeDB:
    def __init__(self):
        self.events=[]

    async def insert_event(self, *args):
        self.events.append(args)


def test_stalled_one_symbol_reconnects_and_resubscribes(monkeypatch):
    async def scenario():
        # A healthy BTC book and ticker traffic cannot conceal silent ETH.
        ack={"op":"subscribe","success":True}
        btc={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":1000,
             "data":{"seq":1,"u":1,"b":[["100","2"]],"a":[["101","2"]]}}
        ticker={"topic":"tickers.BTCUSDT","ts":3000000,"data":{"markPrice":"100"}}
        first=FakeSocket([ack,btc,ticker])
        # New socket uses an earlier exchange timestamp and a partial ticker.
        # It must not inherit old markPrice or stale-timestamp guard.
        new_ticker={"topic":"tickers.BTCUSDT","ts":2000000,"data":{"lastPrice":"200"}}
        fresh_book={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":4000000,
                    "data":{"seq":1,"u":1,"b":[["200","3"]],"a":[["201","4"]]}}
        second=FakeSocket([ack,fresh_book,new_ticker])
        connections=FakeConnections([first,second])
        monkeypatch.setattr(module.websockets,"connect",connections)
        async def no_network_wait():
            return None
        monkeypatch.setattr(module,"wait_for_internet",no_network_wait)
        async def immediate_backoff(_delay):
            return None
        monkeypatch.setattr(module.asyncio,"sleep",immediate_backoff)
        clock=[0.0]
        class Clock:
            def time(self):
                return clock[0]
        monkeypatch.setattr(module.asyncio,"get_running_loop",lambda:Clock())
        async def fake_wait_for(awaitable,timeout):
            # Consume actual frames, then emulate 10s poll timeouts.
            if connections.opened==1 and not first.frames:
                awaitable.close()
                clock[0]+=10
                raise asyncio.TimeoutError
            if connections.opened==2 and not second.frames:
                awaitable.close()
                raise asyncio.CancelledError
            return await awaitable
        monkeypatch.setattr(module.asyncio,"wait_for",fake_wait_for)
        db=FakeDB()
        with pytest.raises(asyncio.CancelledError):
            await module.MicrostructureCollector(db).run_batch(["BTCUSDT","ETHUSDT"])
        assert connections.opened==2
        assert first.closed
        books=[event for event in db.events if event[2]=="orderbook_snapshot"]
        assert len(books)==2
        assert books[0][1]==1000
        assert books[1][1]==4000000
        assert books[1][3]["mid"]==200.5
        tickers=[event for event in db.events if event[2]=="derivatives_ticker"]
        assert len(tickers)==2
        assert tickers[0][3]["mark_price"]=="100"
        assert tickers[1][3]["last_price"]=="200"
        assert tickers[1][3]["mark_price"] is None
        assert second.sent[0]["args"]==[
            "orderbook.50.BTCUSDT","tickers.BTCUSDT",
            "orderbook.50.ETHUSDT","tickers.ETHUSDT",
        ]
    asyncio.run(scenario())
