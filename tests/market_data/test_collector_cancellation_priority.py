"""Caller cancellation wins over admission revocation; fake transport/sink only."""
import asyncio
import pytest
from market_data.collector import PublicTradeCollector
from market_data.raw_capture import RawCaptureError
from test_selection_rotation import SharedSink,Socket

def managed(monkeypatch):
 for key,value in dict(UNIFIED_MODULE_ID='market_data',UNIFIED_MODULE_VERSION='fixture',UNIFIED_RELEASE_ID='fixture',UNIFIED_INSTANCE_TOKEN='b'*64).items():monkeypatch.setenv(key,value)

@pytest.mark.asyncio
@pytest.mark.parametrize('boundary',['current','run'])
async def test_consumed_pending_cancellation_wins_before_admission_is_read(monkeypatch,boundary):
 managed(monkeypatch)
 class Admission:
  calls=0
  def require_current(self):self.calls+=1;return False
 class ForbiddenSink:
  async def store_capture(self,**kwargs):raise AssertionError('no store in boundary predicate test')
 admission=Admission();collector=PublicTradeCollector(ForbiddenSink(),symbol='BTCUSDT',source_revision='a'*40,startup_admission=admission)
 task=asyncio.current_task();assert task.cancelling()==0
 task.cancel()
 try:
  try:await asyncio.sleep(0)
  except asyncio.CancelledError:pass # Models completed wait_for returning with a pending request.
  assert task.cancelling()==1
  with pytest.raises(asyncio.CancelledError):
   if boundary=='current':collector._current()
   else:await collector.run()
  assert admission.calls==0
 finally:
  while task.cancelling():task.uncancel() # Test task cleanup only, never product policy.

@pytest.mark.asyncio
@pytest.mark.parametrize('max_frames',[1,2])
async def test_cancel_at_completed_subscription_callback_preserves_unknown_cleanup(tmp_path,monkeypatch,max_frames):
 managed(monkeypatch)
 class Admission:
  current=True
  def require_current(self):return self.current
 admission=Admission();sink=SharedSink(tmp_path/'wal');socket=Socket(asyncio.Event());owned=[]
 async def connector(endpoint):return socket
 async def ready(*args):
  admission.current=False
  owned[0].cancel()
 collector=PublicTradeCollector(sink,symbol='BTCUSDT',source_revision='a'*40,connector=connector,max_frames=max_frames,on_subscription_ready=ready,startup_admission=admission)
 task=asyncio.create_task(collector.run());owned.append(task)
 with pytest.raises(asyncio.CancelledError):await task
 assert task.cancelled() and socket.closed
 assert len(sink.rows)==1 and sink.wal.recover()==[]
 assert collector.recorder.metrics()['stop_reason']=='storage_unknown'
 with pytest.raises(RawCaptureError,match='RAW_CAPTURE_STORAGE_OUTCOME_UNKNOWN'):collector.require_known_outcome()


@pytest.mark.asyncio
async def test_valid_admission_allows_known_disconnect_during_caller_cancellation(tmp_path,monkeypatch):
 from market_data.raw_capture import decode_observation
 import json
 managed(monkeypatch)
 class Admission:
  def require_current(self):return True
 sink=SharedSink(tmp_path/'wal');socket=Socket(asyncio.Event());owned=[];trace=[]
 async def connector(endpoint):return socket
 async def ready(*args):owned[0].cancel()
 collector=PublicTradeCollector(sink,symbol='BTCUSDT',source_revision='a'*40,connector=connector,max_frames=1,on_subscription_ready=ready,startup_admission=Admission())
 wrapper=type(collector.recorder.sink);original=wrapper.store_capture
 async def observed(self,**kwargs):
  task=asyncio.current_task();kind=decode_observation(kwargs['observation_bytes'])['kind']
  trace.append(dict(kind=kind,same_collector_task=task is owned[0],cancelling=task.cancelling()))
  return await original(self,**kwargs)
 monkeypatch.setattr(wrapper,'store_capture',observed)
 task=asyncio.create_task(collector.run());owned.append(task)
 with pytest.raises(asyncio.CancelledError):await task
 print('RAW_CLEANUP_CONTEXT='+json.dumps(trace))
 assert task.cancelled() and socket.closed
 assert [decode_observation(raw)['kind'] for raw,payload in sink.rows]==['frame','disconnect']
 assert collector.recorder.metrics()['stop_reason']!='storage_unknown'
 collector.require_known_outcome()
 assert sink.wal.recover()==[]
