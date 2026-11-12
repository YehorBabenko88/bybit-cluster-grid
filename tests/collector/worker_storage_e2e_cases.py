"""Explicit actual Worker/raw/A4 composition in new retained developer state.

No protected service, loops, subprocesses or provider SDKs. Caller pins both roots.
"""
import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


def complete(coro):
    try:
        try:
            coro.send(None)
        except StopIteration as result:
            return result.value
        raise AssertionError('unexpected suspension')
    finally:
        coro.close()


@contextmanager
def actual_grid():
    root=Path(__file__).resolve().parents[2]/'grid'
    prefix='_a3_actual_collector_grid'
    if any(name==prefix or name.startswith(prefix+'.') for name in sys.modules):
        raise ValueError('unexpected cached Grid source')
    package_spec=importlib.util.spec_from_file_location(prefix,root/'__init__.py',
        submodule_search_locations=[str(root)])
    package=importlib.util.module_from_spec(package_spec)
    sys.modules[prefix]=package
    loaded=[prefix]
    try:
        package_spec.loader.exec_module(package)
        for leaf in ('models','public_trade_validation','continuity','raw_capture','worker'):
            alias=prefix+'.'+leaf
            spec=importlib.util.spec_from_file_location(alias,root/(leaf+'.py'))
            module=importlib.util.module_from_spec(spec);sys.modules[alias]=module;loaded.append(alias)
            spec.loader.exec_module(module);setattr(package,leaf,module)
        yield package
    finally:
        for name in reversed(loaded):sys.modules.pop(name,None)


class SyntheticAdapter:
    """Finite in-memory fixture only; no source I/O or network implementation."""
    def frames(self):
        trade=json.dumps({'topic':'publicTrade.BTCUSDT','data':[
            {'T':1794441600000,'s':'BTCUSDT','p':'100','v':'2','S':'Buy','i':'synthetic-1'}]},
            separators=(',',':')).encode()
        return (trade,trade)


def make_suite(storage_source_root,scratch_parent):
    source=Path(storage_source_root);parent=Path(scratch_parent)
    if not source.is_absolute() or not parent.is_absolute() or parent.exists():
        raise ValueError('explicit exact source and new exclusive scratch required')
    if any(name=='unified_system' or name.startswith('unified_system.') for name in sys.modules):
        raise ValueError('unexpected cached Storage modules')
    raw_source=source/'unified_system/storage/raw_capture.py'
    if hashlib.sha256(raw_source.read_bytes()).hexdigest()!='8af7b96a57f0b84329e8914fe40b41f3804c12722d87f906cb4d25c70e6e2174':
        raise ValueError('Storage source drift')
    sys.path.insert(0,str(source))
    try:
        from unified_system.journal import Journal
        from unified_system.storage.object_store import ObjectStore
        from unified_system.storage.raw_capture import RawCaptureAdapter,RawCaptureProfile
    finally:
        sys.path.remove(str(source))

    class ActualWorkerStorageTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):parent.mkdir(exist_ok=False)

        def context(self,name,grid):
            root=parent/name;root.mkdir(exist_ok=False)
            store=ObjectStore.create(root/'archive',store_id='96dce424-a40b-4f25-8500-26738dd278e5')
            journal=Journal(root/'capture.sqlite');journal.initialize()
            profile=RawCaptureProfile(sqlite_headroom_bytes=262144,inventory_file_limit=128)
            sink=RawCaptureAdapter(store,journal,profile)
            ticks=iter(range(1,100));calls=[]
            def factory(symbol,endpoint):
                calls.append((symbol,endpoint))
                return grid.raw_capture.RawCaptureRecorder(sink,
                    instrument=dict(exchange='bybit',category='linear',symbol='BTCUSDT',instrument_version='1'),
                    producer_source_revision='573e3ff84b50941f5929e9c69b37a01fca60ccdb',
                    source_kind='SYNTHETIC',endpoint=endpoint,profile=grid.raw_capture.RawCaptureProfile(16,4194304,1048576,16384,2),
                    clock=lambda:('2026-11-12T00:00:00.000Z',next(ticks)),
                    connection_id_factory=lambda:'39e675b0-27c9-446b-ae15-4f919dfdbec4')
            worker=grid.worker.Worker(launch_profile='grid.data-only-collector.v1',raw_capture_factory=factory)
            return root,store,journal,profile,sink,worker,calls

        def receive(self,worker,frames):
            return complete(worker.receive_offline(frames,symbol='BTCUSDT',
                endpoint='synthetic://bybit/linear',observed_at_ms=1794441600000))

        def test_exact_duplicate_occurrences_idempotent_link_and_reopen(self):
            with actual_grid() as grid:
                root,store,journal,profile,sink,worker,calls=self.context('duplicates',grid)
                frames=SyntheticAdapter().frames()
                result=self.receive(worker,frames)
                self.assertEqual(len(calls),1)
                self.assertEqual([batch[0].trade_id for batch in result['batches']],['synthetic-1','synthetic-1'])
                rows=journal.read();self.assertEqual(len(rows),5)
                facts=[complete(sink.read_capture(row['receipt']['observation_sha256'])) for row in rows]
                frame_facts=[f for f in facts if f.payload_bytes is not None]
                self.assertEqual([f.payload_bytes for f in frame_facts],list(frames))
                self.assertEqual(frame_facts[0].payload_sha256,hashlib.sha256(frames[0]).hexdigest())
                self.assertNotEqual(frame_facts[0].observation_sha256,frame_facts[1].observation_sha256)
                reopened=RawCaptureAdapter(ObjectStore.open(root/'archive',store_id='96dce424-a40b-4f25-8500-26738dd278e5'),Journal(root/'capture.sqlite'),profile)
                last=facts[-1]
                self.assertEqual(complete(reopened.read_capture(last.observation_sha256)).observation_bytes,last.observation_bytes)
                replay=complete(reopened.store_capture(observation_bytes=last.observation_bytes,payload_bytes=last.payload_bytes))
                self.assertEqual(replay.journal_record_digest,last.journal_record_digest)
                self.assertEqual(len(Journal(root/'capture.sqlite').read()),5)
                with self.assertRaisesRegex(RuntimeError,'ALREADY_USED'):self.receive(worker,frames)
                self.assertEqual(len(calls),1)

        def test_invalid_frame_gap_and_local_readback_remain_explicit(self):
            with actual_grid() as grid:
                _,_,journal,_,sink,worker,_=self.context('gap',grid)
                result=self.receive(worker,(b'{bad',SyntheticAdapter().frames()[0]))
                facts=[complete(sink.read_capture(row['receipt']['observation_sha256'])) for row in journal.read()]
                values=[json.loads(f.observation_bytes) for f in facts]
                self.assertEqual([v['kind'] for v in values],['frame','gap_observation','frame','validated','disconnect'])
                self.assertTrue(result['metrics']['gap_open'])
                self.assertEqual(result['metrics']['publication'],'LOCAL_UNATTESTED')
                for fact in facts:
                    self.assertFalse(fact.publication_confirmed)
                    self.assertEqual(fact.durability,'UNKNOWN')

        def test_cancel_before_second_store_retains_first_raw_and_latches_worker(self):
            with actual_grid() as grid:
                _,_,journal,_,sink,worker,calls=self.context('cancel',grid)
                actual=sink.store_capture;count=0
                async def cancel_second(**kwargs):
                    nonlocal count
                    count+=1
                    if count==2:raise asyncio.CancelledError()
                    return await actual(**kwargs)
                sink.store_capture=cancel_second
                with self.assertRaises(asyncio.CancelledError):self.receive(worker,SyntheticAdapter().frames())
                self.assertEqual(len(journal.read()),1)
                self.assertEqual(worker.raw_capture_failure,'COLLECTOR_OFFLINE_UNCERTAIN')
                with self.assertRaisesRegex(RuntimeError,'ALREADY_USED'):self.receive(worker,SyntheticAdapter().frames())
                self.assertEqual(len(calls),1)

    return unittest.defaultTestLoader.loadTestsFromTestCase(ActualWorkerStorageTests)
