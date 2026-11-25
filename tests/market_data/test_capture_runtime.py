"""Synthetic application frames only: no sockets, subprocesses or databases."""
import asyncio
from hashlib import sha256
import json
from types import SimpleNamespace
import unittest

from market_data.collector import PublicTradeCollector
from market_data.raw_capture import RawCaptureError, decode_observation


ACK = json.dumps({'op': 'subscribe', 'success': True})
TRADE = json.dumps({'topic': 'publicTrade.BTCUSDT', 'data': [
    {'s': 'BTCUSDT', 'T': 1000, 'p': '100.00000000000000000001',
     'v': '0.00000000000000000001', 'S': 'Buy', 'i': 'one'}]})


class Sink:
    def __init__(self, fail_at=None):
        self.rows = []
        self.fail_at = fail_at

    async def store_capture(self, *, observation_bytes, payload_bytes):
        self.rows.append((observation_bytes, payload_bytes))
        if len(self.rows) == self.fail_at:
            raise OSError('injected outcome unknown')
        digest = sha256(observation_bytes).hexdigest()
        return SimpleNamespace(observation_bytes=observation_bytes, payload_bytes=payload_bytes,
            observation_sha256=digest, observation_byte_count=len(observation_bytes),
            payload_sha256=None if payload_bytes is None else sha256(payload_bytes).hexdigest(),
            payload_byte_count=len(payload_bytes or b''), journal_record_digest=digest,
            classification='LOCAL_UNATTESTED', durability='UNKNOWN', local_content_verified=True,
            publication_confirmed=False, native_authority_verified=False, replica_eligible=False)


class Frames:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def recv(self):
        return next(self.rows)

    async def send(self, raw):
        self.sent.append(json.loads(raw))


class CaptureRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, rows, sink=None):
        sink = sink or Sink()
        frames = Frames(rows)
        calls = []

        async def connector(endpoint):
            calls.append(endpoint)
            return frames

        collector = PublicTradeCollector(sink, symbol='BTCUSDT', source_revision='a' * 40,
            connector=connector, clock_ms=lambda: 2000, max_frames=len(rows))
        return await collector.run(), sink, frames, calls

    async def test_exact_original_payload_precedes_validated_record(self):
        result, sink, frames, calls = await self.run_fixture([ACK, TRADE])
        decoded = [decode_observation(raw) for raw, _ in sink.rows]
        self.assertEqual([row['kind'] for row in decoded], ['frame', 'frame', 'validated', 'disconnect'])
        self.assertEqual(sink.rows[1][1], TRADE.encode())
        self.assertEqual(result['accepted_trade_observations'], 1)
        self.assertEqual(result['coverage'], 'UNKNOWN')
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['trading_authorized'])
        self.assertEqual(frames.sent, [{'op': 'subscribe', 'args': ['publicTrade.BTCUSDT']}])
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(row['schema'].startswith('market_data.') for row in decoded))

    async def test_pre_ack_or_bad_batch_never_produces_validated_receipt(self):
        bad = json.loads(TRADE)
        bad['data'].append(dict(bad['data'][0], s='ETHUSDT'))
        for rows in ([TRADE], [ACK, json.dumps(bad)]):
            sink = Sink()
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                await self.run_fixture(rows, sink)
            kinds = [decode_observation(raw)['kind'] for raw, _ in sink.rows]
            self.assertNotIn('validated', kinds)
            self.assertIn('gap_observation', kinds)

    async def test_storage_outcome_unknown_never_reconnects_or_emits_acceptance(self):
        sink = Sink(fail_at=2)
        with self.assertRaises(RawCaptureError):
            await self.run_fixture([ACK, TRADE], sink)
        self.assertEqual(len(sink.rows), 2)
        self.assertNotIn('validated', [decode_observation(raw)['kind'] for raw, _ in sink.rows])

    async def test_stalled_persistence_has_bounded_unknown_outcome(self):
        class Stalled:
            async def store_capture(self, **kwargs):
                await asyncio.Event().wait()

        async def connector(endpoint):
            return Frames([ACK])

        collector = PublicTradeCollector(Stalled(), symbol='BTCUSDT', source_revision='a' * 40,
            connector=connector, max_frames=1, persist_timeout=0.01)
        with self.assertRaises(TimeoutError):
            await collector.run()
        self.assertTrue(collector.recorder.metrics()['failed'])
        self.assertEqual(collector.recorder.metrics()['observations_stored'], 0)


class BackfillCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_page_without_launch_bound_never_attests_complete(self):
        from unittest.mock import patch
        from market_data import market_backfill
        statements = []

        class Pool:
            async def execute(self, *args):
                statements.append(args)

        async def empty(*args, **kwargs):
            return []

        with patch.object(market_backfill, 'fetch_kline_page', empty):
            result = await market_backfill.backfill_symbol(
                Pool(), 'https://api.bybit.com', {'symbol': 'BTCUSDT'}, max_pages=1)
        self.assertFalse(result['complete'])
        self.assertEqual(statements[-1][3], 'waiting_source')
