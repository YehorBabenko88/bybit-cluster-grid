"""Bounded offline tests; fake sink, no asyncio.run/network/filesystem sink."""
import copy
import asyncio
import hashlib
import importlib
import json
from types import SimpleNamespace
import unittest

IDENTITY = dict(exchange='bybit', category='linear', symbol='BTCUSDT', instrument_version='1')
CID = '96dce424-a40b-4f25-8500-26738dd278e5'
CID2 = '39e675b0-27c9-446b-ae15-4f919dfdbec4'

def complete(coro):
    try:
        try: coro.send(None)
        except StopIteration as stop: return stop.value
        raise AssertionError('unexpected await suspension; no event-loop fallback')
    finally: coro.close()

class Sink:
    def __init__(self): self.records = []; self.fail = False; self.tamper = False
    async def store_capture(self, *, observation_bytes, payload_bytes):
        if self.fail: raise OSError('synthetic sink failure')
        self.records.append((observation_bytes, payload_bytes))
        return SimpleNamespace(observation_bytes=observation_bytes, payload_bytes=payload_bytes,
            observation_sha256=hashlib.sha256(observation_bytes).hexdigest(),
            observation_byte_count=len(observation_bytes),
            payload_sha256=None if payload_bytes is None else hashlib.sha256(payload_bytes).hexdigest(),
            payload_byte_count=0 if payload_bytes is None else len(payload_bytes),
            journal_record_digest='a'*64, classification='LOCAL_UNATTESTED',
            local_content_verified=True, publication_confirmed=self.tamper,
            native_authority_verified=False, replica_eligible=False, durability='UNKNOWN')

class RecorderTests(unittest.TestCase):
    def setUp(self):
        try: self.m = importlib.import_module('grid.raw_capture')
        except ModuleNotFoundError as error:
            if error.name == 'grid.raw_capture': self.fail('required bounded raw capture adapter is absent')
            raise
        self.sink = Sink()
        self.n = 0
        self.ids = iter([CID, CID2])
        def clock():
            self.n += 1
            return '2026-11-12T00:00:00.000Z', self.n
        self.capture = self.m.RawCaptureRecorder(self.sink, instrument=IDENTITY,
            producer_source_revision='d6b72b66ff1b85b7e6b956568342ad6bd8bfcfbe',
            source_kind='SYNTHETIC', endpoint='synthetic://bybit/linear',
            profile=self.m.RawCaptureProfile(16,4194304,1048576,16384,2),
            clock=clock, connection_id_factory=lambda: next(self.ids))
        self.capture.begin_connection()

    def frame(self, raw=b'not-json'): return complete(self.capture.frame(raw))
    def observation(self, index=-1): return json.loads(self.sink.records[index][0])

    def test_exact_text_binary_empty_and_distinct_occurrences(self):
        for raw in ('not-json', b'\xff\x00', b'', b'not-json'):
            self.frame(raw)
        self.assertEqual([r[1] for r in self.sink.records], [b'not-json',b'\xff\x00',b'',b'not-json'])
        self.assertEqual(self.observation(0)['payload_kind'], 'TEXT_UTF8_REENCODED_NOT_WIRE')
        self.assertEqual(self.observation(2)['payload_sha256'], hashlib.sha256(b'').hexdigest())
        self.assertEqual(len({r[0] for r in self.sink.records}), 4)
        self.assertIsNone(self.observation()['sequence'])

    def test_codec_roundtrip_and_independent_instrument_copy(self):
        self.frame(); raw = self.sink.records[0][0]
        self.assertEqual(self.m.encode_observation(self.m.decode_observation(raw)), raw)
        self.assertFalse(raw.endswith(b'\n'))
        self.assertEqual(self.observation()['instrument'], IDENTITY)

    def test_codec_rejects_noncanonical_duplicate_numeric_and_trailing_bytes(self):
        self.frame(); raw = self.sink.records[0][0]
        bad = [raw+b'\n', raw.replace(b':',b': ',1),
               raw.replace(b'"observation_index":"1"',b'"observation_index":1'),
               raw.replace(b'"payload_bytes":"8"',b'"payload_bytes":8.0'),
               b'{"schema":"x",'+raw[1:]]
        for value in bad:
            with self.subTest(raw=value[:40]):
                with self.assertRaises(self.m.RawCaptureError): self.m.decode_observation(value)

    def test_codec_rejects_calendar_upper_bound_newline_alias_and_null_violation(self):
        self.frame(); original = self.observation()
        changes = [('received_at_utc','2026-02-30T00:00:00.000Z'),
            ('received_at_utc','2026-11-12T00:00:00.000Z\n'),
            ('observation_index','9223372036854775808'),('received_monotonic_ns','01'),
            ('connection_id',CID+'\n'),('payload_sha256',None),('sequence','1')]
        for key,value in changes:
            item = copy.deepcopy(original); item[key] = value
            with self.subTest(key=key,value=value):
                with self.assertRaises(self.m.RawCaptureError): self.m.encode_observation(item)

    def test_validation_preserves_original_receive_clock_and_real_exchange_fields(self):
        ref = self.frame()
        complete(self.capture.validated(ref, exchange_event_ms=1767225600000, sequence=20, update_id=11))
        obs = self.observation()
        self.assertEqual(obs['kind'],'validated')
        self.assertEqual(obs['frame_metadata_sha256'], ref.metadata_sha256)
        self.assertEqual(obs['exchange_event_at_utc'],'2026-01-01T00:00:00.000Z')
        self.assertEqual(obs['sequence'],'20')
        self.assertEqual(obs['received_monotonic_ns'], '1')
        self.assertIsNone(self.sink.records[-1][1])

    def test_gap_remains_in_history_after_resync(self):
        ref = self.frame()
        complete(self.capture.gap('sequence_invalid', ref))
        complete(self.capture.validated(ref, sequence=20, update_id=1, resync=True))
        self.assertEqual([json.loads(r[0])['kind'] for r in self.sink.records], ['frame','gap_observation','resync'])
        self.assertEqual(self.observation()['reason'],'after_gap')
        self.assertFalse(self.capture.metrics()['gap_open'])

    def test_sink_failure_keeps_received_not_durable_and_is_terminal(self):
        self.sink.fail = True
        with self.assertRaises(self.m.RawCaptureError): self.frame()
        metrics = self.capture.metrics()
        self.assertIsNotNone(metrics['last_frame_received_utc'])
        self.assertIsNone(metrics['last_raw_readback_utc'])
        self.assertTrue(metrics['failed'])
        self.assertFalse(metrics['gap_durable'])
        self.sink.fail = False
        with self.assertRaises(self.m.RawCaptureError): self.frame()
        self.assertEqual(self.sink.records, [])

    def test_false_publication_readback_is_not_accepted(self):
        self.sink.tamper = True
        with self.assertRaises(self.m.RawCaptureError): self.frame()
        self.assertIsNone(self.capture.metrics()['last_raw_readback_utc'])

    def test_oversized_frame_stops_without_forwarding_payload(self):
        with self.assertRaises(self.m.RawCaptureError): self.frame(b'x'*1048577)
        self.assertTrue(all(raw is None for _,raw in self.sink.records))
        self.assertTrue(self.capture.metrics()['failed'])

    def test_reserved_control_slots_are_inside_total_sixteen(self):
        for _ in range(14): self.frame(b'')
        with self.assertRaises(self.m.RawCaptureError): self.frame(b'')
        self.assertLessEqual(len(self.sink.records),16)
        self.assertTrue(self.capture.metrics()['failed'])

    def test_reconnect_does_not_reset_count_and_preserves_disconnect(self):
        self.frame(); complete(self.capture.disconnect('transport_error'))
        self.capture.begin_connection(); self.frame()
        self.assertEqual(len(self.sink.records),3)
        self.assertEqual(self.capture.metrics()['observations_stored'],3)
        self.assertEqual(self.observation()['connection_id'], CID2)
        self.assertEqual(self.observation()['observation_index'],'1')
        self.assertIsNotNone(self.observation()['previous_metadata_sha256'])

    def test_foreign_frame_reference_stops_without_control_write(self):
        with self.assertRaises(self.m.RawCaptureError): complete(self.capture.validated(object()))
        self.assertEqual(self.sink.records, [])

    def test_budget_and_busy_reentry_are_fail_closed(self):
        self.capture._busy = True
        with self.assertRaises(self.m.RawCaptureError): self.frame()
        self.assertEqual(self.sink.records, [])

    def test_profile_refuses_expansion_bool_and_missing_limits(self):
        for values in [(17,4194304,1048576,16384,2),(16,4194305,1048576,16384,2),(True,1,1,1,0),(16,1,1,1,0)]:
            with self.subTest(values=values):
                with self.assertRaises(self.m.RawCaptureError): self.m.RawCaptureProfile(*values)

    def test_readback_hash_mismatch_stops_before_durable_advance(self):
        original = self.sink.store_capture
        async def wrong(**kwargs):
            facts = await original(**kwargs); facts.payload_sha256 = '0'*64; return facts
        self.sink.store_capture = wrong
        with self.assertRaises(self.m.RawCaptureError): self.frame()
        self.assertIsNone(self.capture.metrics()['last_raw_readback_utc'])

    def test_mutated_returned_metrics_do_not_change_recorder(self):
        self.frame(); result = self.capture.metrics(); result['observations_stored']=999
        self.assertEqual(self.capture.metrics()['observations_stored'],1)

    def test_sink_cancellation_propagates_original_and_keeps_unknown(self):
        async def cancelled(**_): raise asyncio.CancelledError
        self.sink.store_capture=cancelled
        with self.assertRaises(asyncio.CancelledError): self.frame()
        self.assertTrue(self.capture.metrics()['failed'])
        self.assertIsNone(self.capture.metrics()['last_raw_readback_utc'])

    def test_regressing_monotonic_receive_clock_stops(self):
        self.frame()
        self.capture._clock=lambda:('2026-11-12T00:00:00.000Z',0)
        with self.assertRaises(self.m.RawCaptureError): self.frame()
        self.assertEqual(len(self.sink.records),1)

    def test_readback_clock_is_separate_from_receive_clock(self):
        ticks=iter([('2026-11-12T00:00:00.000Z',1),('2026-11-12T00:00:01.000Z',2)])
        self.capture._clock=lambda:next(ticks)
        self.frame()
        self.assertEqual(self.capture.metrics()['last_raw_readback_utc'],'2026-11-12T00:00:01.000Z')
        self.assertEqual(self.capture.metrics()['last_frame_received_utc'],'2026-11-12T00:00:00.000Z')

    def test_nonboolean_resync_mode_is_rejected_before_write(self):
        ref=self.frame()
        with self.assertRaises(self.m.RawCaptureError): complete(self.capture.validated(ref,resync='yes'))
        self.assertEqual(len(self.sink.records),1)
