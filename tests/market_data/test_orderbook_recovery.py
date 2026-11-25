"""Deterministic fault injection for autonomous orderbook transport recovery."""
import asyncio
import json
import pytest
from market_data.orderbook_stream import OrderBookStream
from market_data.raw_capture import RawCaptureRecorder, RawCaptureProfile
from test_capture_runtime import Sink

def make_stream(*args, **kwargs):
    sink = Sink()
    def factory(symbol, endpoint):
        return RawCaptureRecorder(sink, instrument={"exchange":"bybit","category":"linear",
            "symbol":symbol,"instrument_version":"1"}, producer_source_revision="a"*40,
            source_kind="PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED", endpoint=endpoint,
            profile=RawCaptureProfile(16,4194304,1048576,16384,2))
    return OrderBookStream(*args,capture_factory=factory,**kwargs)


def packet(kind, uid, seq, *, bad=False):
    return json.dumps({"topic": "orderbook.50.BTCUSDT", "type": kind, "ts": 1,
        "data": {"s": "BTCUSDT", "u": uid, "seq": seq,
                 "b": [["100", "NaN" if bad else "1"]], "a": [["101", "1"]]}})


class FakeSocket:
    def __init__(self, messages):
        self.messages = iter([json.dumps({"op":"subscribe","success":True}), *messages])
        self.closed = False
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        self.closed = True
    async def send(self, *_):
        pass
    async def recv(self):
        try:
            item = next(self.messages)
        except StopIteration:
            await asyncio.sleep(3600)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.asyncio
async def test_invalid_delta_forces_new_connection_and_snapshot(monkeypatch):
    sockets = [
        FakeSocket([packet("snapshot", 1, 1), packet("delta", 2, 2, bad=True),
                    packet("delta", 3, 3)]),
        FakeSocket([packet("snapshot", 10, 10)])
    ]
    created = list(sockets)
    stop = asyncio.Event()
    events, gaps = [], []
    async def on_book(symbol, book, ts):
        events.append((symbol, book.valid, book.update_id))
        if len(events) == 2:
            stop.set()
    async def on_gap(symbols, reason):
        gaps.append(reason)
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: sockets.pop(0))
    stream = make_stream(on_book, on_gap, backoff_base=0.001, backoff_max=0.01)
    await asyncio.wait_for(stream.run(["BTCUSDT"], stop), 3)
    assert events == [("BTCUSDT", True, 1), ("BTCUSDT", True, 10)]
    assert stream.connection_epoch == 2
    assert any("invalid" in g for g in gaps)
    assert all(s.closed for s in created)


@pytest.mark.asyncio
async def test_silent_connected_feed_reconnects(monkeypatch):
    sockets = [FakeSocket([]), FakeSocket([packet("snapshot", 3, 3)])]
    stop = asyncio.Event()
    observed = []
    async def on_book(symbol, book, ts):
        observed.append(book.update_id)
        stop.set()
    async def on_gap(*_):
        pass
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: sockets.pop(0))
    stream = make_stream(on_book, on_gap, silence_timeout=0.01,
                             backoff_base=0.001, backoff_max=0.01)
    await asyncio.wait_for(stream.run(["BTCUSDT"], stop), 3)
    assert observed == [3]
    assert stream.connection_epoch == 2


@pytest.mark.asyncio
async def test_shutdown_interrupts_reconnect_backoff(monkeypatch):
    stop = asyncio.Event()
    async def failed_connect():
        raise OSError("network down")
    class BrokenSocket:
        async def __aenter__(self):
            await failed_connect()
        async def __aexit__(self, *_):
            pass
    calls = 0
    async def on_gap(*_):
        nonlocal calls
        calls += 1
        if calls >= 2:
            stop.set()
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: BrokenSocket())
    stream = make_stream(lambda *_: None, on_gap)
    await asyncio.wait_for(stream.run(["BTCUSDT"], stop), 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_message", [
    packet("delta", 2, 2, bad=True),
    packet("delta", 1, 2),
    packet("delta", 2, 1),
    packet("snapshot", 3, 3, bad=True),
    "{broken json",
])
async def test_fault_requires_new_epoch_and_snapshot(monkeypatch, bad_message):
    sockets = [
        FakeSocket([packet("snapshot", 1, 1), bad_message,
                    packet("delta", 4, 4)]),
        FakeSocket([packet("snapshot", 10, 10)])
    ]
    created = list(sockets)
    stop = asyncio.Event()
    updates, gaps = [], []
    async def on_book(symbol, book, ts):
        updates.append((book.update_id, book.valid))
        if len(updates) == 2:
            stop.set()
    async def on_gap(symbols, reason):
        gaps.append(reason)
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: sockets.pop(0))
    stream = make_stream(on_book, on_gap, backoff_base=0.001, backoff_max=0.01)
    await asyncio.wait_for(stream.run(["BTCUSDT"], stop), 3)
    assert updates == [(1, True), (10, True)]
    assert stream.connection_epoch == 2
    assert all(sock.closed for sock in created)
    assert any("UNVERIFIED" in reason for reason in gaps)


@pytest.mark.asyncio
async def test_failed_handshakes_preserve_exponential_backoff(monkeypatch):
    class StopProbe:
        def __init__(self):
            self.calls = 0
        def is_set(self):
            return self.calls >= 4
        async def wait(self):
            self.calls += 1
            raise asyncio.TimeoutError
    class BrokenSocket:
        async def __aenter__(self):
            raise ConnectionError("handshake rejected")
        async def __aexit__(self, *_):
            pass
    async def on_gap(*_):
        pass
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: BrokenSocket())
    monkeypatch.setattr("market_data.orderbook_stream.random.uniform",
                        lambda a, b: 1.0)
    delays = []
    original_wait_for = asyncio.wait_for
    async def measured_wait_for(awaitable, timeout):
        if isinstance(stop, StopProbe) and timeout <= 0.4:
            delays.append(timeout)
        return await original_wait_for(awaitable, timeout)
    # Use an event that immediately raises TimeoutError to avoid real sleeps.
    stop = StopProbe()
    monkeypatch.setattr("market_data.orderbook_stream.asyncio.wait_for",
                        measured_wait_for)
    stream = make_stream(lambda *_: None, on_gap,
                             backoff_base=0.1, backoff_max=0.4)
    await stream.run(["BTCUSDT"], stop)
    assert delays == [0.1, 0.2, 0.4, 0.4]


@pytest.mark.asyncio
async def test_other_symbol_traffic_does_not_hide_silent_book(monkeypatch):
    # A busy connection can keep delivering unrelated messages while the
    # subscribed book is silent; the watchdog must check on every iteration.
    from types import SimpleNamespace
    clock=[0.0];unrelated=[];gaps=[]
    # Replace only this module binding; asyncio retains its real monotonic clock.
    monkeypatch.setattr("market_data.orderbook_stream.time",
                        SimpleNamespace(monotonic=lambda:clock[0]))
    class BusySocket(FakeSocket):
        async def recv(self):
            clock[0]+=0.004
            unrelated.append(clock[0])
            await asyncio.sleep(0)
            return json.dumps({"topic": "publicTrade.BTCUSDT", "data": []})
    sockets = [BusySocket([]), FakeSocket([packet("snapshot", 8, 8)])]
    stop = asyncio.Event()
    updates = []
    async def on_book(symbol, book, ts):
        updates.append(book.update_id)
        stop.set()
    async def on_gap(symbols,reason):
        gaps.append(reason)
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: sockets.pop(0))
    stream = make_stream(on_book, on_gap, silence_timeout=0.01,
                             backoff_base=0.001, backoff_max=0.01)
    await asyncio.wait_for(stream.run(["BTCUSDT"], stop), 2)
    assert updates == [8]
    assert stream.connection_epoch == 2
    assert len(unrelated)>=3
    assert any("silent" in reason for reason in gaps)


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp", ["not-a-timestamp", None, True, 0, -1, 1.5, "1"])
async def test_malformed_timestamp_never_publishes_valid_book(monkeypatch, timestamp):
    malformed = json.loads(packet("snapshot", 1, 1))
    malformed["ts"] = timestamp
    sockets = [
        FakeSocket([json.dumps(malformed), packet("delta", 2, 2)]),
        FakeSocket([packet("snapshot", 10, 10)])
    ]
    stop = asyncio.Event()
    updates, gaps = [], []
    async def on_book(symbol, book, ts):
        updates.append((book.update_id, ts))
        stop.set()
    async def on_gap(symbols, reason):
        gaps.append(reason)
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: sockets.pop(0))
    stream = make_stream(on_book, on_gap, backoff_base=0.001, backoff_max=0.01)
    await asyncio.wait_for(stream.run(["BTCUSDT"], stop), 3)
    assert updates == [(10, 1)]
    assert stream.connection_epoch == 2
    assert any("timestamp" in reason for reason in gaps)


@pytest.mark.asyncio
async def test_published_snapshot_is_immutable_and_not_mutated_by_later_delta(monkeypatch):
    from decimal import Decimal
    sockets = [FakeSocket([
        packet("snapshot", 1, 1),
        packet("delta", 2, 2),
    ])]
    stop = asyncio.Event()
    published = []
    async def on_book(symbol, book, ts):
        published.append(book)
        if len(published) == 2:
            stop.set()
    async def on_gap(*_):
        pass
    monkeypatch.setattr("market_data.orderbook_stream.websockets.connect",
                        lambda *a, **kw: sockets.pop(0))
    stream = make_stream(on_book, on_gap)
    await asyncio.wait_for(stream.run(["BTCUSDT"], stop), 2)
    first, second = published
    assert first is not second
    assert first.update_id == 1 and second.update_id == 2
    assert first.bids[Decimal("100")] == Decimal("1")
    with pytest.raises(TypeError):
        first.bids[Decimal("100")] = Decimal("99")
    with pytest.raises(Exception):
        first.update_id = 99
