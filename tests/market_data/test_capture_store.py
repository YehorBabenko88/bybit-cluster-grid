"""Driver-boundary fault injection, not PostgreSQL operational qualification."""
from contextlib import asynccontextmanager
import unittest

from market_data.capture_store import CaptureStore
from test_capture_runtime import Sink
from market_data.raw_capture import RawCaptureRecorder, RawCaptureProfile, RawCaptureError


class Connection:
    def __init__(self, fail_commit=False):
        self.info = type("Info",(),{"transaction_status":0})()
        self.rows = {}
        self.fail_commit = fail_commit
        self.committed = False
        self.closed = False
        self.pending = None

    @asynccontextmanager
    async def transaction(self):
        original = dict(self.rows)
        try:
            yield self
            if self.fail_commit:
                raise OSError('injected commit failure')
            self.committed = True
        except BaseException:
            self.rows = original
            raise

    async def execute(self, statement, parameters):
        if statement.startswith('INSERT'):
            digest, observation, payload, connection_id, ordinal = parameters
            self.rows.setdefault(digest, (observation, payload))
        else:
            self.pending = self.rows.get(parameters[0])
        return self

    async def fetchone(self):
        return self.pending

    async def close(self):
        self.closed = True


def recorder(sink):
    return RawCaptureRecorder(sink,
        instrument={'exchange': 'bybit', 'category': 'linear', 'symbol': 'BTCUSDT', 'instrument_version': '1'},
        producer_source_revision='a' * 40, source_kind='SYNTHETIC', endpoint='synthetic://bybit/linear',
        profile=RawCaptureProfile(16, 4194304, 1048576, 16384, 2))


class CaptureStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_ack_is_after_commit_and_exact_retry_does_not_duplicate(self):
        connection = Connection()
        store = CaptureStore(connection)
        capture = recorder(store)
        capture.begin_connection()
        await capture.frame(b'original')
        self.assertTrue(connection.committed)
        observation, payload = next(iter(connection.rows.values()))
        readback = await store.store_capture(observation_bytes=observation, payload_bytes=payload)
        self.assertTrue(readback.local_content_verified)
        self.assertEqual(len(connection.rows), 1)
        self.assertEqual(readback.payload_bytes, b'original')
        await store.close()
        self.assertTrue(connection.closed)
        with self.assertRaises(RuntimeError):
            await store.store_capture(observation_bytes=observation, payload_bytes=payload)

    async def test_commit_failure_prevents_ack_and_stops_recorder(self):
        connection = Connection(fail_commit=True)
        capture = recorder(CaptureStore(connection))
        capture.begin_connection()
        with self.assertRaises(RawCaptureError):
            await capture.frame(b'original')
        self.assertEqual(connection.rows, {})
        self.assertTrue(capture.metrics()['failed'])
        self.assertEqual(capture.metrics()['observations_stored'], 0)
