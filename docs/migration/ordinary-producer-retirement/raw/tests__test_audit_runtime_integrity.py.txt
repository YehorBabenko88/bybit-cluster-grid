import logging
import threading
from dataclasses import replace

import pytest

from strattester.engine.jobs import Job, JobState
from strattester.engine.resource_manager import ResourceSnapshot
from strattester.engine.scheduler import Scheduler
from strattester.engine.executor import _coverage_ready
from strattester.marketdata.sqlite_store import Candle, SQLiteMarketStore
from strattester.marketdata.sharded_store import ShardedMarketStore
from strattester.persistence.sqlite_state_store import SQLiteStateStore
from strattester.research.execution import ExecutionPolicy, Signal, simulate_trade
from strattester.runtime.lifecycle import Lifecycle
from strattester.runtime.worker import WorkerRuntime


def snapshot():
    gb = 1024**3
    return ResourceSnapshot(16*gb, 8*gb, 20*gb, 0)


@pytest.mark.parametrize('state', [JobState.LEASED, JobState.RUNNING])
def test_restart_recovers_an_expired_only_queue(tmp_path, state):
    store = SQLiteStateStore.open(tmp_path/'jobs.db')
    job = Job.new('backtest', state=state, lease_owner='old', lease_until=1, lease_token=4)
    store.put_job(job)
    calls = []
    worker = WorkerRuntime(store, Scheduler(store), calls.append, Lifecycle(),
                           logging.getLogger('audit'), snapshot, execution_mode='thread')
    try:
        assert worker.run_once() == 1
        assert [j.id for j in calls] == [job.id]
        recovered = store.get_job(job.id)
        assert recovered.state == JobState.COMPLETE
        assert recovered.lease_token == 5
    finally:
        store.close()


def test_scheduler_candidate_does_not_overwrite_a_concurrent_renewal(tmp_path):
    store = SQLiteStateStore.open(tmp_path/'jobs.db')
    job = Job.new('backtest', state=JobState.RUNNING, lease_owner='old', lease_until=1, lease_token=4)
    store.put_job(job)
    try:
        candidates = Scheduler(store).ready_jobs(snapshot())
        assert [j.id for j in candidates] == [job.id]
        assert store.get_job(job.id) == job
        assert store.renew_lease(job.id, 'old', 4, now=2, lease_seconds=100)
        assert store.claim_ready_jobs('new', now=3, job_ids=[job.id]) == []
        assert store.get_job(job.id).lease_owner == 'old'
    finally:
        store.close()


@pytest.mark.parametrize('ohlc', [(-.002, -.001, -.003, -.002), (0, 0, 0, 0)])
def test_premium_index_accepts_finite_signed_values(tmp_path, ohlc):
    store = SQLiteMarketStore.open(tmp_path/'market.db')
    try:
        stats = store.upsert_price_klines('premium_index', 'BTCUSDT', [(0, *ohlc)])
        assert (stats.accepted, stats.rejected) == (1, 0)
        assert store.coverage('BTCUSDT', 'premium_index').count == 1
        assert store.upsert_price_klines('mark_price', 'BTCUSDT', [(0, *ohlc)]).rejected == 1
    finally:
        store.close()


@pytest.mark.parametrize('dataset', ['premium_index', 'mark_price', 'index_price'])
def test_price_klines_reject_nonfinite_values(tmp_path, dataset):
    store = SQLiteMarketStore.open(tmp_path/'market.db')
    try:
        assert store.upsert_price_klines(dataset, 'BTCUSDT', [(0, 1, float('inf'), 1, 1)]).rejected == 1
    finally:
        store.close()


def test_incomplete_candle_does_not_satisfy_history_or_strategy_readers(tmp_path):
    store = SQLiteMarketStore.open(tmp_path/'market.db')
    candle = Candle('BTCUSDT', '1m', 0, 100, 101, 99, 100, 1, complete=False)
    try:
        store.upsert_candles([candle])
        assert not _coverage_ready(store, 'BTCUSDT', 'candles', '1m', 0, 0)
        assert list(store.iter_candles('BTCUSDT')) == []
        store.upsert_candles([replace(candle, complete=True)])
        assert _coverage_ready(store, 'BTCUSDT', 'candles', '1m', 0, 0)
        assert len(list(store.iter_candles('BTCUSDT'))) == 1
    finally:
        store.close()


def test_migration_does_not_promote_a_stale_corrected_candle(tmp_path, monkeypatch):
    legacy = SQLiteMarketStore.open(tmp_path/'legacy.db')
    original = Candle('BTCUSDT', '1m', 0, 100, 102, 99, 100, 1)
    legacy.upsert_candles([original])
    store = ShardedMarketStore(tmp_path/'shards', legacy_store=legacy)
    shard = store.for_symbol('BTCUSDT')
    write = shard.upsert_candles
    changed = False

    def correct_after_copy(records):
        nonlocal changed
        result = write(records)
        if not changed:
            changed = True
            legacy.upsert_candles([replace(original, close=101)])
        return result

    monkeypatch.setattr(shard, 'upsert_candles', correct_after_copy)
    try:
        with pytest.raises(RuntimeError, match='source changed'):
            store.migrate_legacy_candles('BTCUSDT', batch_size=1)
        assert not store.manifest.ready('BTCUSDT')
        assert list(store.iter_candles('BTCUSDT'))[0].close == 101
        store.migrate_legacy_candles('BTCUSDT', batch_size=1)
        assert store.manifest.ready('BTCUSDT')
        assert list(store.iter_candles('BTCUSDT'))[0].close == 101
    finally:
        store.close()
        legacy.close()


def test_routed_write_waits_for_promotion_then_uses_the_shard(tmp_path, monkeypatch):
    legacy_path = tmp_path/'legacy.db'
    root = tmp_path/'shards'
    legacy = SQLiteMarketStore.open(legacy_path)
    original = Candle('BTCUSDT', '1m', 0, 100, 102, 99, 100, 1)
    legacy.upsert_candles([original])
    store = ShardedMarketStore(root, legacy_store=legacy)
    attempted = threading.Event()
    completed = threading.Event()
    errors = []

    def writer():
        other_legacy = SQLiteMarketStore.open(legacy_path)
        other = ShardedMarketStore(root, legacy_store=other_legacy)
        try:
            attempted.set()
            other.upsert_candles([replace(original, close=101)])
        except Exception as exc:
            errors.append(exc)
        finally:
            other.close()
            other_legacy.close()
            completed.set()

    fingerprint = store._dataset_fingerprints
    thread = None

    def interleave(target, symbol, *args):
        nonlocal thread
        if target is store.for_symbol(symbol) and thread is None:
            thread = threading.Thread(target=writer)
            thread.start()
            assert attempted.wait(3)
            assert not completed.wait(.1), 'writer must wait until routing promotion commits'
        return fingerprint(target, symbol, *args)

    monkeypatch.setattr(store, '_dataset_fingerprints', interleave)
    try:
        store.migrate_legacy_candles('BTCUSDT')
        assert completed.wait(3)
        assert not errors
        assert list(store.iter_candles('BTCUSDT'))[0].close == 101
        assert list(legacy.iter_candles('BTCUSDT'))[0].close == 100
    finally:
        if thread is not None:
            thread.join(3)
        store.close()
        legacy.close()


@pytest.mark.parametrize('side,sl,tp,bar', [
    ('long', 95, 105, {'t':60000, 'open':110, 'high':112, 'low':94, 'close':96}),
    ('short', 105, 95, {'t':60000, 'open':90, 'high':106, 'low':88, 'close':104}),
])
def test_intrabar_limit_fill_cannot_exit_at_an_earlier_opening_gap(side, sl, tp, bar):
    signal = Signal(0, side, 'limit', 100, sl, tp)
    trade = simulate_trade(signal, [bar], ExecutionPolicy(60000, fee_rate=0))
    assert trade.entry_price == 100
    assert trade.exit_reason == 'SL'
    assert trade.exit_price == sl
    assert trade.gross_pnl == -5
