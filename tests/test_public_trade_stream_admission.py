"""Local synthetic public-feed fixtures; no exchange calls or real provenance."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from grid import worker as module
from grid.segment_wal import SegmentWAL
from grid.storage import Storage


ACK={'op':'subscribe','success':True,'args':['publicTrade.BTCUSDT']}


def frame(*,topic='BTCUSDT',price='100',qty='2',side='Buy',stamp=600000,trade_id='one'):
    return {'topic':'publicTrade.'+topic,'data':[{'s':topic,'T':stamp,'p':price,'v':qty,'S':side,'i':trade_id}]}


class Socket:
    def __init__(self,frames,clock):self.frames=list(frames);self.clock=clock
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def send(self,raw):pass
    async def recv(self):
        if not self.frames:raise asyncio.CancelledError
        item=self.frames.pop(0)
        if isinstance(item,tuple):item,self.clock[0]=item
        return json.dumps(item)


class Sink:
    def __init__(self):self.rows=[]
    async def save(self,row):self.rows.append(row)


async def run(monkeypatch,frames,*,sink=None,more_connections=(),clock=None,setup=None):
    clock=clock or [663.]
    sockets=[Socket(frames,clock),*(Socket(items,clock) for items in more_connections)]
    connects=[]
    def connect(*args,**kwargs):connects.append(kwargs);return sockets.pop(0)
    async def online():pass
    async def pause(*args):pass
    monkeypatch.setattr(module,'wait_for_internet',online)
    monkeypatch.setattr(module.websockets,'connect',connect)
    monkeypatch.setattr(module.time,'time',lambda:clock[0])
    monkeypatch.setattr(module.asyncio,'sleep',pause)
    worker=module.Worker.__new__(module.Worker)
    worker.meta={'BTCUSDT':{'tick_size':.1}};worker.micro_wanted=set()
    worker.storage=sink or Sink()
    worker.pressure=SimpleNamespace(state='NORMAL',bad_ticks=0,observe_symbol=lambda *args,**kwargs:None)
    if setup is not None:setup(worker)
    with pytest.raises(asyncio.CancelledError):await worker.trade_stream('BTCUSDT')
    return worker.storage,connects


def test_preack_trades_preserved_in_arrival_order(monkeypatch):
    async def scenario():
        sink,_=await run(monkeypatch,[frame(price='100',trade_id='early'),ACK,
            frame(price='200',stamp=600200,trade_id='later'),
            (frame(stamp=660000,trade_id='next-minute'),663.)],clock=[600.5])
        row=next(row for row in sink.rows if row['start_ms']==600000)
        assert row['trade_count']==2 and row['open']==100 and row['close']==200
    asyncio.run(scenario())


def test_other_public_trade_topic_cannot_be_relabelled(monkeypatch):
    async def scenario():
        sink,_=await run(monkeypatch,[ACK,frame(topic='ETHUSDT')])
        assert sink.rows==[]
    asyncio.run(scenario())


def test_invalid_trade_entire_batch_rejected_before_mutation(monkeypatch):
    async def scenario():
        malformed=frame(qty='-2',side='Unexpected')
        malformed['data'].insert(0,frame(trade_id='valid-before-invalid')['data'][0])
        sink,_=await run(monkeypatch,[ACK,malformed])
        assert sink.rows==[]
    asyncio.run(scenario())


def test_wal_refusal_keeps_finalized_row_until_durable_admission(monkeypatch,tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path/'wal');attempts=[];queue=[]
        class Spool:
            def __init__(self):self.calls=0
            def ratio(self):self.calls+=1;return 1. if self.calls==1 else 0.
            async def append(self,row):return await wal.append(row)
        class Queue:
            async def put(self,*args):queue.append(args)
        storage=Storage.__new__(Storage);storage.spool=Spool();storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock()
        class ActualSink:
            async def save(self,row):attempts.append(row);await storage.save(row)
        await run(monkeypatch,[ACK,frame()],sink=ActualSink(),more_connections=[[ACK,frame()]])
        recovered=wal.recover()
        assert len(recovered)==1 and recovered[0][1]['trade_count']==1
        assert len(queue)==1 and len(attempts)==2
    asyncio.run(scenario())


@pytest.mark.parametrize('field,value',[('T',True),('T',600000.5),('T','bad'),('T',-1),('T',10**18),
    ('p','NaN'),('p','Infinity'),('p',0),('v',False),('v','-1'),('v','0'),('S','Unknown'),('s','ETHUSDT'),('i',[])])
def test_malformed_batch_does_not_touch_aggregator_or_continuity(monkeypatch,field,value):
    async def scenario():
        mutations=[]
        original=module.FootprintBuilder;original_guard=module.TradeContinuity
        class Builder(original):
            def add(self,trade):mutations.append('aggregate');return super().add(trade)
        class Guard(original_guard):
            def observe(self,stamp):mutations.append('continuity');return super().observe(stamp)
        monkeypatch.setattr(module,'FootprintBuilder',Builder);monkeypatch.setattr(module,'TradeContinuity',Guard)
        malformed=frame(trade_id='invalid');malformed['data'][0][field]=value
        malformed['data'].insert(0,frame(trade_id='valid-prefix')['data'][0])
        sink,_=await run(monkeypatch,[ACK,malformed])
        assert mutations==[] and sink.rows==[]
    asyncio.run(scenario())


def test_rejected_batch_marks_next_valid_observation_degraded(monkeypatch):
    async def scenario():
        sink,_=await run(monkeypatch,[ACK,frame(qty='-2'),frame(trade_id='accepted')])
        assert len(sink.rows)==1 and sink.rows[0]['quality_status']=='DEGRADED'
        assert 'invalid_public_trade_frame' in sink.rows[0]['quality_reasons']
    asyncio.run(scenario())


@pytest.mark.parametrize('setting,value',[('MAX_ACK_BYTES',1),('MAX_ACK_FRAMES',1)])
def test_subscription_buffer_bounds_reconnect_without_replaying_old_epoch(monkeypatch,setting,value):
    async def scenario():
        monkeypatch.setattr(module,setting,value)
        sink,connects=await run(monkeypatch,[frame(trade_id='early-1'),frame(trade_id='early-2'),ACK],
            more_connections=[[ACK,frame(price='200',trade_id='fresh')]])
        assert len(connects)==2 and len(sink.rows)==1
        assert sink.rows[0]['trade_count']==1 and sink.rows[0]['open']==200
        assert sink.rows[0]['quality_status']=='DEGRADED'
        assert connects[0]['max_size']==1024*1024
    asyncio.run(scenario())


def test_open_minute_bound_rejects_whole_batch_before_mutation(monkeypatch):
    async def scenario():
        monkeypatch.setattr(module,'MAX_OPEN_MINUTES',1)
        malformed=frame();malformed['data'].append(frame(stamp=660000,trade_id='other-minute')['data'][0])
        sink,_=await run(monkeypatch,[ACK,malformed])
        assert sink.rows==[]
    asyncio.run(scenario())


def test_pending_wal_admission_timeout_is_cancellable_without_new_connection(monkeypatch):
    async def scenario():
        second=asyncio.Event();attempts=[];connects=[]
        class BlockedSink:
            async def save(self,row):
                attempts.append(row)
                if len(attempts)==2:second.set()
                await asyncio.Event().wait()
        clock=[663.];socket=Socket([ACK,frame()],clock)
        def connect(*args,**kwargs):connects.append(1);return socket
        async def online():pass
        async def pause(*args):pass
        monkeypatch.setattr(module,'PERSIST_TIMEOUT_SECONDS',.02)
        monkeypatch.setattr(module,'wait_for_internet',online);monkeypatch.setattr(module.websockets,'connect',connect)
        monkeypatch.setattr(module.time,'time',lambda:clock[0]);monkeypatch.setattr(module.asyncio,'sleep',pause)
        worker=module.Worker.__new__(module.Worker);worker.meta={'BTCUSDT':{'tick_size':.1}};worker.micro_wanted=set()
        worker.storage=BlockedSink();worker.pressure=SimpleNamespace(state='NORMAL',bad_ticks=0,observe_symbol=lambda *args,**kwargs:None)
        task=asyncio.create_task(worker.trade_stream('BTCUSDT'))
        try:
            await asyncio.wait_for(second.wait(),1)
            assert len(connects)==1 and attempts[0] is attempts[1]
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await asyncio.wait_for(task,1)
    asyncio.run(scenario())


def test_ack_crossing_minute_deadline_does_not_finalize_before_buffer_tail(monkeypatch):
    async def scenario():
        sink,_=await run(monkeypatch,[frame(price='100',trade_id='early-1'),
            frame(price='200',stamp=600200,trade_id='early-2'),(ACK,663.)],clock=[600.5])
        row=next(row for row in sink.rows if row['start_ms']==600000)
        assert row['trade_count']==2 and row['open']==100 and row['close']==200
    asyncio.run(scenario())


def test_replayed_finalized_batch_cannot_clear_unpublished_quality_reason(monkeypatch):
    async def scenario():
        sink,_=await run(monkeypatch,[ACK,frame(stamp=659900,trade_id='original'),
            frame(stamp=659950,qty='-2',trade_id='invalid'),frame(stamp=659900,trade_id='original'),
            (frame(stamp=660000,trade_id='fresh'),723.)])
        row=next(row for row in sink.rows if row['start_ms']==660000)
        assert row['quality_status']=='DEGRADED' and 'invalid_public_trade_frame' in row['quality_reasons']
    asyncio.run(scenario())


def test_automatic_pressure_cancel_retains_minute_for_reassigned_stream(monkeypatch,tmp_path):
    from grid.pressure import PressureController,NORMAL,CRITICAL
    async def scenario():
        real_sleep=asyncio.sleep;refused=asyncio.Event();wal=SegmentWAL(tmp_path/'wal');queued=[]
        class Spool:
            full=True
            def ratio(self):
                if self.full:refused.set();return 1.
                return 0.
            async def append(self,row):return await wal.append(row)
        class Queue:
            async def put(self,*args):queued.append(args)
        storage=Storage.__new__(Storage);storage.spool=Spool();storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock()
        clock=[663.]
        sockets=[Socket([ACK,frame()],clock),Socket([ACK,(frame(stamp=660000,trade_id='fresh'),723.)],clock)]
        async def online():pass
        async def pause(*args):await real_sleep(0)
        monkeypatch.setattr(module,'wait_for_internet',online)
        monkeypatch.setattr(module.websockets,'connect',lambda *args,**kwargs:sockets.pop(0))
        monkeypatch.setattr(module.time,'time',lambda:clock[0]);monkeypatch.setattr(module.asyncio,'sleep',pause)
        worker=module.Worker.__new__(module.Worker)
        worker.meta={'BTCUSDT':{'tick_size':.1}};worker.micro_wanted=set();worker.storage=storage
        worker.pressure=PressureController();worker.operator_stopped=False;worker.bootstrap_paused=False
        worker.assignment_lock=asyncio.Lock();worker.wanted={'BTCUSDT'};worker.pressure_drained=set()
        worker.last_assignment_heartbeat=None;worker.micro_signature=();worker.micro_tasks=[]
        first=asyncio.create_task(worker.trade_stream('BTCUSDT'));worker.trade_tasks={'BTCUSDT':first}
        try:
            await asyncio.wait_for(refused.wait(),1)
            while worker.pressure.state!=CRITICAL:await real_sleep(0)
            await worker._apply_local_pressure();await asyncio.gather(first,return_exceptions=True)
            assert first.cancelled() and worker.pressure_drained=={'BTCUSDT'}
            storage.spool.full=False;worker.pressure.state=NORMAL
            await worker._apply_local_pressure()
            resumed=worker.trade_tasks['BTCUSDT'];await asyncio.wait_for(asyncio.gather(resumed,return_exceptions=True),1)
            recovered=wal.recover()
            assert len(recovered)==2 and all(row['trade_count']==1 for _,row in recovered) and len(queued)==2
            assert recovered[1][1]['quality_status']=='DEGRADED'
        finally:
            for task in worker.trade_tasks.values():task.cancel()
            await asyncio.gather(*worker.trade_tasks.values(),return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize('price,quantities',[('1e308',['1']),('100',['1e308','1e308'])])
def test_finite_numeric_overflow_is_rejected_before_footprint_mutation(monkeypatch,price,quantities):
    async def scenario():
        mutations=[];original=module.FootprintBuilder
        class Builder(original):
            def add(self,trade):mutations.append(trade);return super().add(trade)
        monkeypatch.setattr(module,'FootprintBuilder',Builder)
        message=frame(price=price,qty=quantities[0])
        for index,qty in enumerate(quantities[1:]):message['data'].append(frame(price=price,qty=qty,trade_id='extra-'+str(index))['data'][0])
        sink,_=await run(monkeypatch,[ACK,message],more_connections=[[ACK]])
        assert mutations==[] and sink.rows==[]
    asyncio.run(scenario())


@pytest.mark.parametrize('tick',[0,-1,float('nan'),float('inf'),True])
def test_invalid_tick_rejected_before_connection(monkeypatch,tick):
    async def scenario():
        async def forbidden():raise asyncio.CancelledError
        monkeypatch.setattr(module,'wait_for_internet',forbidden)
        worker=module.Worker.__new__(module.Worker);worker.meta={'BTCUSDT':{'tick_size':tick}}
        with pytest.raises(ValueError):await worker.trade_stream('BTCUSDT')
    asyncio.run(scenario())


def test_numeric_overflow_in_existing_open_bucket_rejects_only_new_batch(monkeypatch):
    async def scenario():
        sink,_=await run(monkeypatch,[ACK,frame(qty='1e308',trade_id='first'),
            frame(qty='1e308',trade_id='overflow'),(frame(stamp=660000,trade_id='next'),663.)],clock=[600.5])
        row=next(row for row in sink.rows if row['start_ms']==600000)
        assert row['trade_count']==1 and row['buy_volume']==1e308 and row['quality_status']=='DEGRADED'
    asyncio.run(scenario())


def test_whole_batch_total_volume_overflow_is_rejected(monkeypatch):
    async def scenario():
        message=frame(qty='1e308');message['data'].append(frame(qty='1e308',stamp=660000,trade_id='other-minute')['data'][0])
        sink,_=await run(monkeypatch,[ACK,message],clock=[723.])
        assert sink.rows==[]
    asyncio.run(scenario())


def test_global_pending_reservation_survives_micro_await_and_blocks_other_mutation(monkeypatch):
    async def scenario():
        entered=asyncio.Event();release=asyncio.Event();mutations=[];real_sleep=asyncio.sleep
        original=module.FootprintBuilder
        class Builder(original):
            def add(self,trade):mutations.append(trade.symbol);return super().add(trade)
        class Micro:
            async def insert_event(self,*args):entered.set();await release.wait()
        clock=[663.];sockets=[Socket([ACK,frame()],clock),
            Socket([{'op':'subscribe','success':True,'args':['publicTrade.ETHUSDT']},frame(topic='ETHUSDT')],clock),
            Socket([{'op':'subscribe','success':True,'args':['publicTrade.ETHUSDT']}],clock)]
        async def online():pass
        async def pause(*args):await real_sleep(0)
        monkeypatch.setattr(module,'FootprintBuilder',Builder);monkeypatch.setattr(module,'MAX_OPEN_MINUTES',1)
        monkeypatch.setattr(module,'wait_for_internet',online);monkeypatch.setattr(module.websockets,'connect',lambda *args,**kwargs:sockets.pop(0))
        monkeypatch.setattr(module.time,'time',lambda:clock[0]);monkeypatch.setattr(module.asyncio,'sleep',pause)
        worker=module.Worker.__new__(module.Worker);worker.meta={symbol:{'tick_size':.1} for symbol in ('BTCUSDT','ETHUSDT')}
        from grid.micro_tape import MicroTapeAggregator
        from grid.models import Trade
        worker.micro_wanted={'BTCUSDT'};worker.micro_tape=MicroTapeAggregator()
        worker.micro_tape.add(Trade('BTCUSDT',599000,100.,1.,'Buy','synthetic-seed'))
        worker.micro_storage=Micro();worker.storage=Sink()
        worker.pressure=SimpleNamespace(state='NORMAL',bad_ticks=0,observe_symbol=lambda *args,**kwargs:None)
        first=asyncio.create_task(worker.trade_stream('BTCUSDT'));second=None
        try:
            await asyncio.wait_for(entered.wait(),1)
            second=asyncio.create_task(worker.trade_stream('ETHUSDT'))
            await asyncio.wait_for(asyncio.gather(second,return_exceptions=True),1)
            assert mutations==['BTCUSDT']
            assert sum(worker._pending_trade_reservations.values())==1
            release.set();await asyncio.wait_for(asyncio.gather(first,return_exceptions=True),1)
            assert len(worker.storage.rows)==1 and worker.storage.rows[0]['symbol']=='BTCUSDT'
            assert not worker._pending_trade_reservations
        finally:
            release.set()
            for task in (first,second):
                if task is not None:task.cancel()
            await asyncio.gather(*(task for task in (first,second) if task is not None),return_exceptions=True)
    asyncio.run(scenario())


def test_cross_minute_cvd_overflow_rejected_before_real_pipeline_mutation(monkeypatch):
    import math
    from grid.micro_tape import MicroTapeAggregator
    async def scenario():
        events=[];tape=MicroTapeAggregator()
        class Micro:
            async def insert_event(self,*args):events.append(args)
        def setup(worker):worker.micro_wanted={'BTCUSDT'};worker.micro_tape=tape;worker.micro_storage=Micro()
        sink,_=await run(monkeypatch,[ACK,frame(qty='1e308',trade_id='first'),
            (frame(qty='1e308',stamp=660000,trade_id='second'),723.),
            (frame(qty='1e308',stamp=720000,trade_id='third'),783.),
            (frame(qty='1',stamp=780000,trade_id='normal-recovery'),843.)],setup=setup)
        assert [row['start_ms'] for row in sink.rows]==[600000,780000]
        assert len(events)==1 and math.isfinite(events[0][3]['cvd'])
        assert sink.rows[-1]['quality_status']=='DEGRADED'
    asyncio.run(scenario())


def test_rejected_cvd_batch_leaves_all_real_tape_symbols_and_footprint_unchanged(monkeypatch):
    import copy
    from grid.micro_tape import MicroTapeAggregator
    from grid.models import Trade
    async def scenario():
        tape=MicroTapeAggregator();tape.add(Trade('BTCUSDT',600000,100.,1e308,'Buy','seed'))
        tape.add(Trade('BTCUSDT',660000,100.,1.,'Buy','current'))
        tape.add(Trade('ETHUSDT',600000,200.,2.,'Sell','other'))
        before=copy.deepcopy((tape.state,tape.cvd));mutations=[];original=module.FootprintBuilder
        class Builder(original):
            def add(self,trade):mutations.append(trade);return super().add(trade)
        monkeypatch.setattr(module,'FootprintBuilder',Builder)
        message=frame(stamp=660100,qty='1',trade_id='valid-prefix')
        message['data'].append(frame(stamp=660200,qty='1e308',trade_id='overflow')['data'][0])
        class Micro:
            async def insert_event(self,*args):pytest.fail('rejected batch persisted micro state')
        def setup(worker):worker.micro_wanted={'BTCUSDT'};worker.micro_tape=tape;worker.micro_storage=Micro()
        sink,_=await run(monkeypatch,[ACK,message],setup=setup)
        assert mutations==[] and sink.rows==[] and (tape.state,tape.cvd)==before
    asyncio.run(scenario())


def test_unknown_oversized_tape_state_rejected_before_copy_or_mutation(monkeypatch):
    from grid.micro_tape import MicroTapeAggregator
    async def scenario():
        tape=MicroTapeAggregator();tape.state['BTCUSDT']={str(i):i for i in range(100)}
        mutations=[];original=module.FootprintBuilder
        class Builder(original):
            def add(self,trade):mutations.append(trade);return super().add(trade)
        monkeypatch.setattr(module,'FootprintBuilder',Builder)
        def setup(worker):worker.micro_wanted={'BTCUSDT'};worker.micro_tape=tape
        sink,_=await run(monkeypatch,[ACK,frame()],more_connections=[[ACK]],setup=setup)
        assert mutations==[] and sink.rows==[] and len(tape.state['BTCUSDT'])==100
    asyncio.run(scenario())


def test_tape_opposite_side_volume_overflow_is_not_hidden_by_zero_delta():
    from grid.micro_tape import MicroTapeAggregator
    from grid.models import Trade
    from grid.public_trade_validation import preflight_tape
    tape=MicroTapeAggregator();tape.add(Trade('BTCUSDT',600000,100.,1e308,'Buy','buy'))
    tape.add(Trade('BTCUSDT',600100,100.,1e308,'Sell','sell'))
    with pytest.raises(ValueError):preflight_tape([],tape,'BTCUSDT')
