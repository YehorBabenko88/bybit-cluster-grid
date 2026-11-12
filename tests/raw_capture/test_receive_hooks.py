"""Actual collector/selected Worker method with inert transport, no event loop."""
import ast
import asyncio
import importlib
import importlib.util
import json
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from collections import deque
from contextlib import contextmanager
from test_recorder import Sink, complete, CID, CID2, IDENTITY

START = 1767225600000
ACK = json.dumps({'op':'subscribe','success':True})
SNAP = json.dumps({'topic':'orderbook.50.BTCUSDT','type':'snapshot','ts':START,
    'data':{'seq':10,'u':10,'b':[['100','2']],'a':[['101','3']]}})
DELTA = json.dumps({'topic':'orderbook.50.BTCUSDT','type':'delta','ts':START+1000,
    'data':{'seq':20,'u':11,'b':[['100','4']],'a':[]}})

@contextmanager
def module_bindings(bindings):
    missing=object(); old={key:sys.modules.get(key,missing) for key in bindings}
    sys.modules.update(bindings)
    try: yield
    finally:
        for key,value in old.items():
            if value is missing: sys.modules.pop(key,None)
            else: sys.modules[key]=value

class Socket:
    def __init__(self,frames,end_error=asyncio.CancelledError):
        self.frames=deque(frames); self.closed=False; self.sent=[]; self.end_error=end_error
    async def __aenter__(self): return self
    async def __aexit__(self,*_): self.closed=True
    async def send(self,raw): self.sent.append(raw)
    async def recv(self):
        if self.frames: return self.frames.popleft()
        raise self.end_error

class HookTests(unittest.TestCase):
    microstructure_source_override = None
    worker_source_override = None
    def setUp(self):
        import grid
        self.parent=grid; self.prior_parent_module=getattr(grid,'microstructure',None)
        self.raw=importlib.import_module('grid.raw_capture')
        self.sink=Sink(); ids=iter([CID,CID2]); tick=iter(range(1,100))
        self.capture=self.raw.RawCaptureRecorder(self.sink,instrument=IDENTITY,
            producer_source_revision='d6b72b66ff1b85b7e6b956568342ad6bd8bfcfbe',
            source_kind='SYNTHETIC',endpoint='synthetic://bybit/linear',
            profile=self.raw.RawCaptureProfile(16,4194304,1048576,16384,2),
            clock=lambda:('2026-11-12T00:00:00.000Z',next(tick)),connection_id_factory=lambda:next(ids))
        self.vendor=ModuleType('websockets'); self.config=ModuleType('grid.config')
        self.config.settings=SimpleNamespace(bybit_ws_url='synthetic://bybit/linear',
            cluster_interval_seconds=60,heartbeat_seconds=1)
        with module_bindings({'websockets':self.vendor,'grid.config':self.config}):
            source=self.microstructure_source_override or Path(__file__).parents[2]/'grid'/'microstructure.py'
            spec=importlib.util.spec_from_file_location('grid.microstructure',source)
            self.module=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.events=[]; self.opens=0

    def test_fake_module_is_not_published_to_shared_grid_package(self):
        self.assertIs(getattr(self.parent,'microstructure',None),self.prior_parent_module)

    def patches(self,socket):
        def connect(*_args,**_kwargs):
            self.opens+=1
            if self.opens>1: raise AssertionError('unexpected reconnect')
            return socket
        async def no_wait(): pass
        async def wait(awaitable,timeout): return await awaitable
        async def sleep(delay):
            if delay!=.05: raise AssertionError('unexpected retry/backoff')
        return [module_bindings({'grid.microstructure':self.module,'websockets':self.vendor,'grid.config':self.config}),
            patch.object(self.module.websockets,'connect',connect,create=True),
            patch.object(self.module,'wait_for_internet',no_wait),
            patch.object(asyncio,'wait_for',wait),patch.object(asyncio,'sleep',sleep),
            patch.object(asyncio,'get_running_loop',lambda:SimpleNamespace(time=lambda:1.0)),
            patch.object(self.module.time,'time',lambda:(START+1000)/1000)]

    def run_collector(self,frames,*,symbols=None,expect_error=None,end_error=asyncio.CancelledError):
        from contextlib import ExitStack
        socket=Socket(frames,end_error)
        outer=self
        class DB:
            async def insert_event(self,*event):
                # Must already have persisted original application frames.
                outer.assertTrue(any(raw is not None for _,raw in outer.sink.records))
                outer.events.append(event)
        with ExitStack() as stack:
            for context in self.patches(socket): stack.enter_context(context)
            try: collector=self.module.MicrostructureCollector(DB(),snapshot_ms=1,
                raw_capture_factory=lambda symbol,endpoint:self.capture)
            except TypeError: self.fail('existing collector lacks approved opt-in raw receive hook')
            with self.assertRaises(expect_error or asyncio.CancelledError):
                complete(collector.run_batch(['BTCUSDT'] if symbols is None else symbols))
        return socket

    def test_original_raw_and_malformed_frame_are_stored_before_derived_event(self):
        socket=self.run_collector([ACK,SNAP,'NOT_JSON',DELTA])
        self.assertEqual([raw for _,raw in self.sink.records if raw is not None],
                         [value.encode('utf-8') for value in [ACK,SNAP,'NOT_JSON',DELTA]])
        observations=[json.loads(raw) for raw,_ in self.sink.records]
        self.assertTrue(any(v['kind']=='gap_observation' and v['reason']=='frame_invalid' for v in observations))
        self.assertEqual(observations[-1]['kind'],'disconnect')
        self.assertTrue(socket.closed)

    def test_storage_failure_is_terminal_not_automatic_reconnect(self):
        self.sink.fail=True
        self.run_collector([ACK,SNAP],expect_error=self.raw.RawCaptureError)
        self.assertEqual(self.opens,1); self.assertEqual(self.events,[])

    def test_duplicate_payload_occurrences_are_not_collapsed_by_receive_hook(self):
        self.run_collector([ACK,SNAP,SNAP])
        frames=[(meta,raw) for meta,raw in self.sink.records if raw is not None]
        self.assertEqual([raw for _,raw in frames],[ACK.encode(),SNAP.encode(),SNAP.encode()])
        self.assertEqual(len({meta for meta,_ in frames}),3)

    def test_multi_symbol_raw_profile_rejects_before_connect(self):
        self.run_collector([],symbols=['BTCUSDT','ETHUSDT'],expect_error=self.raw.RawCaptureError)
        self.assertEqual(self.opens,0)

    def test_missing_exchange_timestamp_is_not_filled_from_local_wall(self):
        frame=json.loads(SNAP); frame.pop('ts')
        self.run_collector([ACK,json.dumps(frame)])
        obs=[json.loads(meta) for meta,_ in self.sink.records if json.loads(meta)['kind']=='resync']
        self.assertEqual(len(obs),1); self.assertIsNone(obs[0]['exchange_event_at_utc'])

    def test_actual_sequence_rejection_and_snapshot_emit_persistent_gap_then_resync(self):
        bad=json.loads(DELTA); bad['data']['seq']=9
        fresh=json.loads(SNAP); fresh['data'].update(seq=30,u=1); fresh['ts']=START+2000
        self.run_collector([ACK,SNAP,json.dumps(bad),json.dumps(fresh)])
        observations=[json.loads(meta) for meta,_ in self.sink.records]
        self.assertTrue(any(v['kind']=='gap_observation' and v['reason']=='sequence_invalid' for v in observations))
        self.assertTrue(any(v['kind']=='resync' and v['reason']=='after_gap' for v in observations))

    def worker_type(self):
        # Execute only actual selected Worker methods; never import its service,
        # credential/ProgramData/bootstrap dependency graph.
        from grid.cluster import FootprintBuilder
        from grid.continuity import TradeContinuity
        from grid import public_trade_validation as validation
        source=Path(self.worker_source_override) if self.worker_source_override is not None else Path(__file__).parents[2]/'grid'/'worker.py'
        tree=ast.parse(source.read_bytes())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Worker')
        names={'trade_stream','_trade_handoff_state','_persist_trade_rows','reconcile','_stop_raw_capture_tasks',
               '_require_full_workload','_raw_capture_for','_record_received_frame'}
        methods=[n for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
        namespace={k:getattr(validation,k) for k in ('validated_tick','MAX_FRAME_BYTES','MAX_ACK_FRAMES',
            'MAX_ACK_BYTES','MAX_OPEN_MINUTES','PERSIST_TIMEOUT_SECONDS','decode_frame','parse_trades','preflight_footprint','preflight_tape')}
        async def no_wait(): pass
        namespace.update(__name__='grid.worker',asyncio=asyncio,json=json,time=self.module.time,deque=deque,settings=self.config.settings,
            FootprintBuilder=FootprintBuilder,TradeContinuity=TradeContinuity,
            backoff_delays=lambda:iter([1]),wait_for_internet=no_wait,
            websockets=self.module.websockets,log=logging.getLogger('raw-hook-test'),
            RawCaptureError=self.raw.RawCaptureError,RawCaptureRecorder=self.raw.RawCaptureRecorder)
        selected=ast.Module(body=[ast.ClassDef(name='Worker',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])
        exec(compile(ast.fix_missing_locations(selected),str(source),'exec'),namespace)
        return namespace['Worker']

    def run_worker(self,frames,*,fail=False):
        from contextlib import ExitStack
        self.sink.fail=fail; worker=self.worker_type()(); socket=Socket(frames)
        worker.meta={'BTCUSDT':{'tick_size':.5}}; worker.raw_capture_factory=lambda symbol,endpoint:self.capture
        worker.storage=object(); worker.micro_wanted=set()
        worker.pressure=SimpleNamespace(observe_symbol=lambda *_a,**_kw:None)
        with ExitStack() as stack:
            for context in self.patches(socket): stack.enter_context(context)
            try: complete(worker.trade_stream('BTCUSDT'))
            except self.raw.RawCaptureError:
                if not fail: raise
            except asyncio.CancelledError:
                if fail: self.fail('existing Worker ignored opted-in raw sink failure')
            else: self.fail('fixture exhaustion must stop actual worker')
        return socket

    def test_actual_worker_raw_failure_does_not_reconnect(self):
        self.run_worker([ACK],fail=True)
        self.assertEqual(self.opens,1)

    def test_actual_worker_captures_individual_trade_frames_including_duplicates(self):
        trade=json.dumps({'topic':'publicTrade.BTCUSDT','data':[{'T':START,'p':'100','v':'2','S':'Buy','i':'a','s':'BTCUSDT'}]})
        self.run_worker([ACK,trade,trade])
        self.assertEqual([raw for _,raw in self.sink.records if raw is not None],[ACK.encode(),trade.encode(),trade.encode()])

    def test_cancel_cleanup_sink_failure_does_not_mask_original_cancellation(self):
        original=self.sink.store_capture
        async def fail_disconnect(**kwargs):
            if json.loads(kwargs['observation_bytes'])['kind']=='disconnect': raise OSError('synthetic close failure')
            return await original(**kwargs)
        self.sink.store_capture=fail_disconnect
        self.run_collector([ACK,SNAP])
        self.assertTrue(self.capture.metrics()['failed'])

    def test_worker_opted_in_factory_cannot_silently_disable_capture(self):
        from contextlib import ExitStack
        worker=self.worker_type()(); worker.meta={'BTCUSDT':{'tick_size':.5}}
        worker.raw_capture_factory=lambda *_:None; worker.storage=object(); worker.micro_wanted=set()
        worker.pressure=SimpleNamespace(observe_symbol=lambda *_a,**_kw:None)
        with ExitStack() as stack:
            for context in self.patches(Socket([ACK])): stack.enter_context(context)
            try: complete(worker.trade_stream('BTCUSDT'))
            except self.raw.RawCaptureError: pass
            except asyncio.CancelledError: self.fail('opted-in capture silently disabled')
            else: self.fail('missing capture binding accepted')
        self.assertEqual(self.opens,0)

    def test_raw_transport_failure_stops_without_legacy_backoff(self):
        self.run_collector([ACK,SNAP],expect_error=self.raw.RawCaptureError,end_error=RuntimeError)
        self.assertEqual(self.opens,1)
        self.assertEqual(json.loads(self.sink.records[-1][0])['kind'],'disconnect')

    def test_supervisor_does_not_restart_a_raw_capture_failure(self):
        worker_type=self.worker_type(); worker=worker_type()
        class FailedTask:
            def done(self): return True
            def result(self): raise self.raw_error('RAW_CAPTURE_STORAGE_OUTCOME_UNKNOWN')
            raw_error=self.raw.RawCaptureError
        worker.trade_tasks={'BTCUSDT':FailedTask()}; worker.micro_tasks=[]
        worker.wanted={'BTCUSDT'}; worker.meta={'BTCUSDT':{'tick_size':.5}}
        worker.micro_wanted=set(); worker.micro_signature=()
        worker.raw_capture_factory=lambda *_:self.capture
        scheduled=[]
        def create(coro):
            coro.close(); scheduled.append(True)
            return SimpleNamespace(done=lambda:False)
        async def gather(*_args,**_kwargs): return []
        with patch.object(asyncio,'create_task',create),patch.object(asyncio,'gather',gather):
            complete(worker.reconcile()); complete(worker.reconcile())
        self.assertEqual(scheduled,[])
        self.assertTrue(worker.raw_capture_failure)

    def test_worker_micro_reconciliation_passes_raw_profile_and_single_symbol_batches(self):
        worker_type=self.worker_type(); worker=worker_type()
        worker.trade_tasks={}; worker.micro_tasks=[]; worker.wanted=set(); worker.meta={}
        worker.micro_wanted={'BTCUSDT','ETHUSDT'}; worker.micro_signature=()
        worker.raw_capture_factory=lambda *_:self.capture; worker.micro_storage=object()
        received=[]; batches=[]
        class Collector:
            def __init__(self,_db,**kwargs): received.append(kwargs.get('raw_capture_factory'))
            async def run_batch(self,batch): batches.append(batch)
        def create(coro):
            complete(coro)
            return SimpleNamespace(done=lambda:False,cancel=lambda:None)
        worker_type.reconcile.__globals__['MicrostructureCollector']=Collector
        self.config.settings.microstructure_snapshot_ms=1000
        with patch.object(asyncio,'create_task',create): complete(worker.reconcile())
        self.assertEqual(received,[worker.raw_capture_factory])
        self.assertEqual(batches,[['BTCUSDT'],['ETHUSDT']])

    def test_cancelled_uncertain_task_is_not_restarted_by_supervisor(self):
        worker=self.worker_type()()
        class CancelledTask:
            def done(self): return True
            def result(self): raise asyncio.CancelledError
        worker.trade_tasks={'BTCUSDT':CancelledTask()}; worker.micro_tasks=[]
        worker.wanted={'BTCUSDT'}; worker.meta={'BTCUSDT':{'tick_size':.5}}
        worker.micro_wanted=set(); worker.micro_signature=()
        factory_calls=[]
        worker.raw_capture_factory=lambda *_:factory_calls.append(True)
        scheduled=[]
        def create(coro): coro.close(); scheduled.append(True); return SimpleNamespace(done=lambda:False)
        async def gather(*_args,**_kwargs): return []
        with patch.object(asyncio,'create_task',create),patch.object(asyncio,'gather',gather):
            complete(worker.reconcile()); complete(worker.reconcile())
        self.assertEqual(scheduled,[]); self.assertEqual(factory_calls,[])
        self.assertTrue(worker.raw_capture_failure)

    def test_crossed_book_persists_gap_before_fresh_snapshot(self):
        crossed=json.loads(DELTA); crossed['data']['b']=[['102','1']]
        fresh=json.loads(SNAP); fresh['data'].update(seq=30,u=1); fresh['ts']=START+2000
        self.run_collector([ACK,SNAP,json.dumps(crossed),json.dumps(fresh)])
        observations=[json.loads(meta) for meta,_ in self.sink.records]
        gaps=[i for i,v in enumerate(observations) if v['kind']=='gap_observation']
        recovered=[i for i,v in enumerate(observations) if v['kind']=='resync' and v['reason']=='after_gap']
        self.assertTrue(gaps and recovered); self.assertLess(gaps[0],recovered[0])

    def test_accumulated_level_overflow_persists_gap_before_snapshot(self):
        large=json.loads(SNAP); large['data']['b']=[[str(n),'1'] for n in range(1,201)]
        large['data']['a']=[['1000','1']]
        overflow=json.loads(DELTA); overflow['data']['b']=[['201','1']]
        fresh=json.loads(SNAP); fresh['data'].update(seq=30,u=1); fresh['ts']=START+2000
        self.run_collector([ACK,json.dumps(large),json.dumps(overflow),json.dumps(fresh)])
        observations=[json.loads(meta) for meta,_ in self.sink.records]
        self.assertTrue(any(v['kind']=='gap_observation' for v in observations))
        self.assertTrue(any(v['kind']=='resync' and v['reason']=='after_gap' for v in observations))

    def test_unknown_raw_task_exception_is_terminal_not_profile_reset(self):
        worker=self.worker_type()()
        class FailedTask:
            def done(self): return True
            def result(self): raise OSError('synthetic pre-connect failure')
        worker.trade_tasks={'BTCUSDT':FailedTask()}; worker.micro_tasks=[]
        worker.wanted={'BTCUSDT'}; worker.meta={'BTCUSDT':{'tick_size':.5}}
        worker.micro_wanted=set(); worker.micro_signature=()
        worker.raw_capture_factory=lambda *_:self.capture
        scheduled=[]
        def create(coro): coro.close(); scheduled.append(True); return SimpleNamespace(done=lambda:False)
        async def gather(*_args,**_kwargs): return []
        with patch.object(asyncio,'create_task',create),patch.object(asyncio,'gather',gather): complete(worker.reconcile())
        self.assertEqual(scheduled,[]); self.assertTrue(worker.raw_capture_failure)

    def test_micro_assignment_cancel_outcome_blocks_replacement_profiles(self):
        worker=self.worker_type()(); worker.trade_tasks={}; worker.wanted=set(); worker.meta={}
        worker.micro_signature=('BTCUSDT',); worker.micro_wanted={'BTCUSDT','ETHUSDT'}
        class PendingTask:
            stopped=False
            def done(self): return self.stopped
            def cancel(self): self.stopped=True
        worker.micro_tasks=[PendingTask()]; worker.micro_storage=object()
        factory_calls=[]; worker.raw_capture_factory=lambda *_:factory_calls.append(True)
        factory=worker.raw_capture_factory
        class Collector:
            def __init__(self,*_args,**_kwargs): pass
            async def run_batch(self,batch): factory(batch[0],'synthetic://bybit/linear')
        worker.reconcile.__func__.__globals__['MicrostructureCollector']=Collector
        self.config.settings.microstructure_snapshot_ms=1000
        async def gather(*tasks,**_kwargs): return [asyncio.CancelledError() for _ in tasks]
        def create(coro): complete(coro); return SimpleNamespace(done=lambda:False)
        with patch.object(asyncio,'gather',gather),patch.object(asyncio,'create_task',create): complete(worker.reconcile())
        self.assertEqual(factory_calls,[]); self.assertTrue(worker.raw_capture_failure)

    def test_trade_removal_cancel_outcome_blocks_later_reassignment(self):
        worker=self.worker_type()(); worker.wanted=set(); worker.meta={'BTCUSDT':{'tick_size':.5}}
        worker.micro_signature=(); worker.micro_wanted=set(); worker.micro_tasks=[]
        class PendingTask:
            stopped=False
            def done(self): return self.stopped
            def cancel(self): self.stopped=True
        worker.trade_tasks={'BTCUSDT':PendingTask()}; worker.raw_capture_factory=lambda *_:self.capture
        scheduled=[]
        def create(coro): coro.close(); scheduled.append(True); return SimpleNamespace(done=lambda:False)
        async def gather(*tasks,**_kwargs): return [asyncio.CancelledError() for _ in tasks]
        with patch.object(asyncio,'gather',gather),patch.object(asyncio,'create_task',create):
            complete(worker.reconcile()); worker.wanted={'BTCUSDT'}; complete(worker.reconcile())
        self.assertEqual(scheduled,[]); self.assertTrue(worker.raw_capture_failure)
