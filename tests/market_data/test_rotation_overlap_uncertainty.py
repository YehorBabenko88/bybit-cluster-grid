"""Actual collector/recorder overlap faults; no provider, process or SQL."""
import asyncio,hashlib,json
import pytest
from market_data.selection_rotation import SelectedInstrument,SelectionPlan,BoundedAcquisitionGroup,RotationController
from market_data.raw_capture import RawCaptureError
from market_data.segment_wal import SegmentWAL
from test_capture_runtime import Sink

class PendingSink(Sink):
    def __init__(self,path,mode):super().__init__();self.wal=SegmentWAL(path);self.mode=mode;self.store_waiting=asyncio.Event()
    async def store_capture(self,**kwargs):
        await self.wal.append(dict(kind='FAKE_ORIGINAL_RAW_PENDING',observation_hex=kwargs['observation_bytes'].hex(),payload_hex=None if kwargs['payload_bytes'] is None else kwargs['payload_bytes'].hex()))
        facts=await super().store_capture(**kwargs)
        if self.mode=='raw_ack_cancel' and kwargs['payload_bytes'] and b'old-unknown' in kwargs['payload_bytes']:
            self.store_waiting.set();await asyncio.Event().wait()
        return facts

def selection(symbol):return SelectionPlan((SelectedInstrument(symbol,'1E-1',1),),2678400000)

async def scenario(tmp_path,mode):
    sink=PendingSink(tmp_path/'wal',mode);old_release=asyncio.Event();replacement_waiting=asyncio.Event();new_ack=asyncio.Event();consumer_waiting=asyncio.Event();groups=[]
    class Socket:
        def __init__(self,symbol):self.symbol=symbol;self.count=0;self.closed=False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):
            self.closed=True
            if self.symbol=='BTCUSDT' and mode=='old_close':
                await sink.wal.append(dict(kind='FAKE_CLOSE_OUTCOME_UNKNOWN'))
                raise RawCaptureError('OLD_CLOSE_OUTCOME_UNKNOWN')
        async def send(self,value):assert json.loads(value)['args']==['publicTrade.'+self.symbol]
        async def recv(self):
            self.count+=1
            if self.count==1:
                if self.symbol=='ETHUSDT':replacement_waiting.set();await new_ack.wait()
                return json.dumps(dict(op='subscribe',success=not(mode=='new_rejected' and self.symbol=='ETHUSDT'),args=['publicTrade.'+self.symbol]))
            if self.symbol=='BTCUSDT':
                await old_release.wait()
                return json.dumps(dict(topic='publicTrade.BTCUSDT',data=[dict(T=1999000,s='BTCUSDT',p='100',v='1',S='Buy',i='old-unknown')]))
            await asyncio.Event().wait()
    def factory(plan):
        symbol=plan.instruments[0].symbol
        async def connector(endpoint):return Socket(symbol)
        def consume_factory(instrument):
            async def consume(trade,**binding):
                await sink.wal.append(dict(kind='FAKE_EXECUTION_COMMIT_PENDING',**binding));consumer_waiting.set()
                if mode=='consumer_ack_cancel':await asyncio.Event().wait()
                raise RuntimeError('OLD_EXECUTION_OUTCOME_UNKNOWN')
            return consume
        # Test budget hierarchy: default readiness budget, one-second fault handshakes.
        group=BoundedAcquisitionGroup(sink,plan,source_revision='a'*40,execution_factory=consume_factory,connector=connector,clock_ms=lambda:2000000,max_frames=2);groups.append(group);return group
    controller=RotationController(factory);replacing=None
    try:
        await controller.rotate(selection('BTCUSDT'));old=controller.current
        replacing=asyncio.create_task(controller.rotate(selection('ETHUSDT')))
        await asyncio.wait_for(replacement_waiting.wait(),1)
        if mode!='old_close':
            old_release.set()
            if mode=='consumer_ack_cancel':await asyncio.wait_for(consumer_waiting.wait(),1)
            elif mode=='raw_ack_cancel':await asyncio.wait_for(sink.store_waiting.wait(),1)
            else:await asyncio.wait_for(old.failure_event.wait(),1)
        before=sink.wal.recover();new_ack.set()
        with pytest.raises(RawCaptureError):await replacing
        assert controller.failed is True and controller.current is old and not old.running
        assert sink.wal.recover()[:len(before)]==before and before
        assert all(task.done() for group in groups for task in group.tasks)
        with pytest.raises(RuntimeError):await controller.rotate(selection('SOLUSDT'))
        assert len(groups)==2
    finally:
        new_ack.set()
        if replacing is not None and not replacing.done():replacing.cancel();await asyncio.gather(replacing,return_exceptions=True)
        await controller.stop()

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['old_before_ready','old_close','new_rejected','consumer_ack_cancel','raw_ack_cancel'])
async def test_old_uncertainty_at_every_overlap_boundary_poison_and_drain(tmp_path,mode):
    await scenario(tmp_path,mode)
