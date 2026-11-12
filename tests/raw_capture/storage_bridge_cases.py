"""Explicit optional cross-repository developer suite, not auto-discovered.

Caller provides exact A4 PR91 source and a NEW owned scratch parent. No service,
provider, event loop, corruption injection or cleanup. Retain created state.
"""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from test_recorder import complete, IDENTITY, CID

A4_RAW_SHA = '8af7b96a57f0b84329e8914fe40b41f3804c12722d87f906cb4d25c70e6e2174'

def make_suite(storage_source_root, scratch_parent):
    source=Path(storage_source_root); parent=Path(scratch_parent)
    if not source.is_absolute() or not parent.is_absolute() or parent.exists() or '..' in parent.parts:
        raise ValueError('exact source and new exclusive scratch required')
    if hashlib.sha256((source/'unified_system/storage/raw_capture.py').read_bytes()).hexdigest()!=A4_RAW_SHA:
        raise ValueError('A4 adapter source pin drift')
    # Explicit caller-selected source dependency; no site/installed fallback.
    sys.path.insert(0,str(source))
    try:
        from unified_system.journal import Journal
        from unified_system.storage.object_store import ObjectStore
        from unified_system.storage.raw_capture import RawCaptureAdapter, RawCaptureProfile
    finally: sys.path.remove(str(source))
    from grid.raw_capture import RawCaptureRecorder, RawCaptureProfile as GridProfile

    class StorageBridgeCases(unittest.TestCase):
        @classmethod
        def setUpClass(cls): parent.mkdir(exist_ok=False)

        def setup_case(self,name):
            root=parent/name; root.mkdir(exist_ok=False)
            store=ObjectStore.create(root/'store',store_id=CID)
            journal=Journal(root/'capture.sqlite'); journal.initialize()
            profile=RawCaptureProfile(sqlite_headroom_bytes=262144,inventory_file_limit=128)
            sink=RawCaptureAdapter(store,journal,profile)
            tick=iter(range(1,100))
            recorder=RawCaptureRecorder(sink,instrument=IDENTITY,
                producer_source_revision='d6b72b66ff1b85b7e6b956568342ad6bd8bfcfbe',
                source_kind='SYNTHETIC',endpoint='synthetic://bybit/linear',
                profile=GridProfile(16,4194304,1048576,16384,2),
                clock=lambda:('2026-11-12T00:00:00.000Z',next(tick)),connection_id_factory=lambda:CID)
            recorder.begin_connection()
            return root,store,journal,profile,sink,recorder

        def test_exact_raw_empty_occurrences_reopen_and_original_link_idempotence(self):
            root,store,journal,profile,sink,recorder=self.setup_case('exact-reopen')
            refs=[complete(recorder.frame(value)) for value in (b'',b'not-json',b'not-json')]
            self.assertEqual(len(journal.read()),3)
            reopened=RawCaptureAdapter(ObjectStore.open(root/'store',store_id=CID),Journal(journal.path),profile)
            facts=[complete(reopened.read_capture(ref.metadata_sha256)) for ref in refs]
            self.assertEqual([f.payload_bytes for f in facts],[b'',b'not-json',b'not-json'])
            self.assertNotEqual(facts[1].observation_sha256,facts[2].observation_sha256)
            self.assertEqual(facts[1].payload_sha256,facts[2].payload_sha256)
            replay=complete(reopened.store_capture(observation_bytes=facts[2].observation_bytes,payload_bytes=facts[2].payload_bytes))
            self.assertEqual(replay.journal_record_digest,facts[2].journal_record_digest)
            self.assertEqual(len(journal.read()),3)
            for f in facts:
                self.assertTrue(f.local_content_verified); self.assertFalse(f.publication_confirmed)
                self.assertFalse(f.native_authority_verified); self.assertEqual(f.durability,'UNKNOWN')

        def test_gap_resync_and_disconnect_are_real_metadata_objects_not_raw_payloads(self):
            root,store,journal,profile,sink,recorder=self.setup_case('gap-observations')
            ref=complete(recorder.frame(b'{malformed'))
            complete(recorder.gap('frame_invalid',ref))
            complete(recorder.validated(ref,sequence=20,update_id=1,resync=True))
            complete(recorder.disconnect('normal_stop'))
            rows=journal.read(); self.assertEqual(len(rows),4)
            facts=[complete(sink.read_capture(row['receipt']['observation_sha256'])) for row in rows]
            self.assertEqual([json.loads(f.observation_bytes)['kind'] for f in facts],
                ['frame','gap_observation','resync','disconnect'])
            self.assertEqual([f.payload_bytes for f in facts],[b'{malformed',None,None,None])
            self.assertEqual(json.loads(facts[2].observation_bytes)['reason'],'after_gap')
            self.assertEqual(recorder.metrics()['physical_hard_quota'],'UNQUALIFIED')

    return unittest.defaultTestLoader.loadTestsFromTestCase(StorageBridgeCases)
