"""In-memory raw-capture/sequence boundary; no real sockets, native tools or DB."""
import asyncio
from hashlib import sha256
import json
import pytest

from market_data.orderbook_stream import OrderBookStream
from market_data.raw_capture import RawCaptureRecorder, RawCaptureProfile, RawCaptureError, decode_observation
from test_capture_runtime import Sink
from test_orderbook_recovery import FakeSocket, packet


def factory(sink):
    def create(symbol, endpoint):
        return RawCaptureRecorder(sink,
            instrument={'exchange': 'bybit', 'category': 'linear', 'symbol': symbol, 'instrument_version': '1'},
            producer_source_revision='a' * 40,
            source_kind='PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED', endpoint=endpoint,
            profile=RawCaptureProfile(16, 4194304, 1048576, 16384, 2))
    return create


def test_transport_cannot_start_without_durable_sink_or_bounded_settings():
    async def callback(*args):
        pass
    with pytest.raises(ValueError, match='DURABLE_CAPTURE_REQUIRED'):
        OrderBookStream(callback, callback)
    for change in ({'silence_timeout': True}, {'persist_timeout': float('nan')},
                   {'backoff_max': float('inf')}, {'depth': True}, {'max_epochs': 9}):
        with pytest.raises(ValueError):
            OrderBookStream(callback, callback, capture_factory=factory(Sink()), **change)


def test_shared_public_decoder_refuses_ambiguous_duplicate_json_fields():
    from market_data.public_trades import decode_frame
    with pytest.raises(ValueError):
        decode_frame('{"topic":"orderbook.50.ETHUSDT","topic":"orderbook.50.BTCUSDT"}')


@pytest.mark.asyncio
async def test_original_frame_and_validation_are_committed_before_callback(monkeypatch):
    sink = Sink()
    stop = asyncio.Event()
    events = []
    original = packet('snapshot', 1, 1)

    async def on_book(symbol, snapshot, timestamp):
        decoded = [decode_observation(raw) for raw, _ in sink.rows]
        assert [entry['kind'] for entry in decoded] == ['frame', 'frame', 'resync']
        assert sink.rows[1][1] == original.encode()
        assert snapshot.capture_sha256 == sha256(sink.rows[1][0]).hexdigest()
        assert snapshot.validation_sha256 == sha256(sink.rows[2][0]).hexdigest()
        assert snapshot.execution_authority is False and snapshot.trading_authorized is False
        assert snapshot.source_status == 'PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED'
        events.append(snapshot)
        stop.set()

    async def on_gap(*args):
        pass

    monkeypatch.setattr('market_data.orderbook_stream.websockets.connect', lambda *a, **kw: FakeSocket([original]))
    stream = OrderBookStream(on_book, on_gap, capture_factory=factory(sink))
    result = await stream.run(['BTCUSDT'], stop)
    assert len(events) == 1 and result['accepted_book_observations'] == 1
    assert result['coverage'] == 'UNKNOWN' and result['source_status'] == 'UNVERIFIED'


@pytest.mark.asyncio
async def test_uncertain_storage_never_reconnects_or_calls_book_consumer(monkeypatch):
    sink = Sink(fail_at=2)
    calls = []

    async def on_book(*args):
        raise AssertionError('uncommitted source cannot reach consumer')

    async def on_gap(*args):
        pass

    def connect(*args, **kwargs):
        calls.append(1)
        return FakeSocket([packet('snapshot', 1, 1)])

    monkeypatch.setattr('market_data.orderbook_stream.websockets.connect', connect)
    stream = OrderBookStream(on_book, on_gap, capture_factory=factory(sink),
                             backoff_base=0.001, backoff_max=0.01)
    with pytest.raises(RawCaptureError):
        await stream.run(['BTCUSDT'], asyncio.Event())
    assert calls == [1]
    assert all(not book.valid for book in stream.books.values())


@pytest.mark.asyncio
async def test_snapshot_before_subscription_ack_never_publishes(monkeypatch):
    class BeforeAck(FakeSocket):
        def __init__(self):
            self.messages = iter([packet('snapshot', 1, 1)])
            self.closed = False

    published = []

    async def on_book(*args):
        published.append(args)

    async def on_gap(*args):
        pass

    sink = Sink()
    monkeypatch.setattr('market_data.orderbook_stream.websockets.connect', lambda *a, **kw: BeforeAck())
    stream = OrderBookStream(on_book, on_gap, capture_factory=factory(sink),
                             max_epochs=1, backoff_base=0.001, backoff_max=0.01)
    result = await stream.run(['BTCUSDT'], asyncio.Event())
    assert published == [] and result['accepted_book_observations'] == 0
    kinds = [decode_observation(raw)['kind'] for raw, _ in sink.rows]
    assert 'resync' not in kinds and 'validated' not in kinds
    assert 'gap_observation' in kinds


@pytest.mark.asyncio
async def test_transport_handshake_timeout_recovers_without_mislabeling_storage(monkeypatch):
    class HandshakeTimeout:
        async def __aenter__(self):
            raise TimeoutError('synthetic transport timeout')

        async def __aexit__(self, *args):
            pass

    sockets = [HandshakeTimeout(), FakeSocket([packet('snapshot', 10, 10)])]
    stop = asyncio.Event()
    published = []

    async def on_book(symbol, snapshot, timestamp):
        published.append(snapshot.update_id)
        stop.set()

    async def on_gap(*args):
        pass

    monkeypatch.setattr('market_data.orderbook_stream.websockets.connect', lambda *a, **kw: sockets.pop(0))
    stream = OrderBookStream(on_book, on_gap, capture_factory=factory(Sink()),
                             backoff_base=0.001, backoff_max=0.01)
    result = await stream.run(['BTCUSDT'], stop)
    assert published == [10] and result['connection_epochs'] == 2


@pytest.mark.asyncio
async def test_consumer_failure_cannot_be_retried_as_transport_reconnect(monkeypatch):
    calls = []

    async def on_book(*args):
        calls.append(1)
        raise OSError('synthetic consumer outcome unknown')

    async def on_gap(*args):
        pass

    monkeypatch.setattr('market_data.orderbook_stream.websockets.connect',
                        lambda *a, **kw: FakeSocket([packet('snapshot', 1, 1)]))
    stream = OrderBookStream(on_book, on_gap, capture_factory=factory(Sink()), max_epochs=2,
                             backoff_base=0.001, backoff_max=0.01)
    with pytest.raises(RuntimeError, match='consumer acknowledgement'):
        await stream.run(['BTCUSDT'], asyncio.Event())
    assert calls == [1]


@pytest.mark.asyncio
async def test_multiple_instruments_keep_capture_identity_and_immutable_snapshots(monkeypatch):
    btc = packet('snapshot', 1, 1)
    eth = json.loads(packet('snapshot', 1, 1))
    eth['topic'] = 'orderbook.50.ETHUSDT'
    eth['data']['s'] = 'ETHUSDT'
    sink = Sink()
    stop = asyncio.Event()
    snapshots = []

    async def on_book(symbol, snapshot, timestamp):
        reference = next(decode_observation(raw) for raw, _ in sink.rows
                         if sha256(raw).hexdigest() == snapshot.capture_sha256)
        assert reference['instrument']['symbol'] == symbol
        snapshots.append(snapshot)
        if len(snapshots) == 3:
            stop.set()

    async def on_gap(*args):
        pass

    monkeypatch.setattr('market_data.orderbook_stream.websockets.connect',
                        lambda *a, **kw: FakeSocket([btc, json.dumps(eth), packet('delta', 2, 2)]))
    stream = OrderBookStream(on_book, on_gap, capture_factory=factory(sink))
    result = await stream.run(['BTCUSDT', 'ETHUSDT'], stop)
    assert [snapshot.symbol for snapshot in snapshots] == ['BTCUSDT', 'ETHUSDT', 'BTCUSDT']
    assert snapshots[0].update_id == 1 and snapshots[2].update_id == 2
    assert {snapshot.connection_epoch for snapshot in snapshots} == {1}
    assert result['accepted_book_observations'] == 3


@pytest.mark.asyncio
async def test_cancellation_closes_fake_transport_without_reconnect(monkeypatch):
    waiting = asyncio.Event()

    class WaitingSocket(FakeSocket):
        async def recv(self):
            if not getattr(self, 'acknowledged', False):
                self.acknowledged = True
                return json.dumps({'op': 'subscribe', 'success': True})
            waiting.set()
            await asyncio.Event().wait()

    socket = WaitingSocket([])
    calls = []

    def connect(*args, **kwargs):
        calls.append(1)
        return socket

    async def callback(*args):
        pass

    monkeypatch.setattr('market_data.orderbook_stream.websockets.connect', connect)
    stream = OrderBookStream(callback, callback, capture_factory=factory(Sink()))
    task = asyncio.create_task(stream.run(['BTCUSDT'], asyncio.Event()))
    await asyncio.wait_for(waiting.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert socket.closed and calls == [1]


def test_versioned_snapshot_preserves_tiny_decimal_strings_without_live_claim():
    from decimal import Decimal
    from market_data.orderbook import OrderBook
    from market_data.orderbook_stream import BookSnapshot
    book = OrderBook('BTCUSDT')
    assert book.apply(dict(type='snapshot', data=dict(s='BTCUSDT', u=1, seq=1,
        b=[['100', '1e-1000']], a=[['101', '1']])))
    payload = BookSnapshot.from_book(book, 'snapshot', epoch=1).payload(1)
    assert payload['schema'] == 'market_data.orderbook.snapshot.v1'
    assert payload['bids'] == [['100', '1E-1000']]
    assert payload['source_status'] == 'CALLER_SUPPLIED_UNATTESTED'
    assert payload['execution_authority'] is False and payload['trading_authorized'] is False
    assert Decimal(payload['bids'][0][1]) == Decimal('1e-1000')
