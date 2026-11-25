"""Actual finite collector + canonical recorder/parser; fake persistence only."""
import asyncio,json
from decimal import Decimal
import pytest
from market_data.synthetic_collector import SyntheticCollector,SYNTHETIC_COLLECTOR_PROFILE
from market_data.raw_capture import RawCaptureRecorder,RawCaptureProfile,RawCaptureError,decode_observation
from test_capture_runtime import Sink

ENDPOINT='synthetic://bybit/linear'
STAMP=1794441600000
def frame(**override):
    row=dict(s='BTCUSDT',T=STAMP,p='0.1',v='1e-1000',S='Buy',i='synthetic-1');row.update(override)
    return json.dumps(dict(topic='publicTrade.BTCUSDT',data=[row]),separators=(',',':')).encode()
def make(sink=None,kind='SYNTHETIC'):
    sink=sink or Sink();calls=[]
    def factory(symbol,endpoint):
        calls.append((symbol,endpoint))
        return RawCaptureRecorder(sink,instrument=dict(exchange='bybit',category='linear',symbol=symbol,instrument_version='1'),producer_source_revision='a'*40,source_kind=kind,endpoint=endpoint,profile=RawCaptureProfile(16,4194304,1048576,16384,2))
    return SyntheticCollector(profile=SYNTHETIC_COLLECTOR_PROFILE,raw_capture_factory=factory),sink,calls
async def receive(collector,frames,**changes):
    args=dict(symbol='BTCUSDT',endpoint=ENDPOINT,observed_at_ms=STAMP);args.update(changes)
    return await collector.receive_offline(frames,**args)

def test_profile_is_explicit_without_worker_or_full_workload_alias():
    import market_data.synthetic_collector as module
    assert SYNTHETIC_COLLECTOR_PROFILE=='market_data.synthetic-collector.v1'
    assert not hasattr(module,'Worker') and not hasattr(module,'COLLECTOR_PROFILE')
    for value in (None,True,'grid.data-only-collector.v1','unknown'):
        with pytest.raises(ValueError):SyntheticCollector(profile=value,raw_capture_factory=lambda *_:None)
    with pytest.raises(ValueError):SyntheticCollector(profile=SYNTHETIC_COLLECTOR_PROFILE,raw_capture_factory=None)
    collector,_,_=make()
    assert all(not hasattr(collector,name) for name in ('run','heartbeat','trade_stream','reconcile','data_first_task','storage','micro_storage'))

@pytest.mark.asyncio
async def test_exact_duplicate_occurrences_use_current_v2_and_one_dto():
    collector,sink,calls=make();raw=frame();result=await receive(collector,(raw,raw))
    assert calls==[('BTCUSDT',ENDPOINT)]
    assert [batch[0].trade_id for batch in result['batches']]==['synthetic-1','synthetic-1']
    assert result['batches'][0][0].price==Decimal('0.1') and result['batches'][0][0].qty==Decimal('1e-1000')
    values=[decode_observation(raw) for raw,_ in sink.rows]
    assert [value['kind'] for value in values]==['frame','validated','frame','validated','disconnect']
    assert all(value['schema']=='market_data.raw-capture-observation.v2' and value['source_kind']=='SYNTHETIC' for value in values)
    assert sink.rows[0][1]==sink.rows[2][1]==raw and sink.rows[0][0]!=sink.rows[2][0]
    assert result['provider_sends']==0 and result['execution_authority'] is False
    with pytest.raises(RuntimeError):await receive(collector,(raw,))
    assert len(calls)==1

@pytest.mark.asyncio
@pytest.mark.parametrize('frames,changes',[([],{}),((b'{}',)*5,{}),((b'x'*1048577,),{}),((b'{}',),{'endpoint':'wss://stream.bybit.com/v5/public/linear'}),((b'{}',),{'symbol':'ETHUSDT'}),((b'{}',),{'observed_at_ms':True})])
async def test_input_refusal_precedes_factory_or_sink(frames,changes):
    collector,sink,calls=make()
    with pytest.raises(ValueError):await receive(collector,frames,**changes)
    assert calls==[] and sink.rows==[]

@pytest.mark.asyncio
async def test_invalid_or_partial_batch_records_gap_without_publishing_prefix():
    collector,sink,_=make();bad=json.loads(frame());bad['data'].append(dict(bad['data'][0],v='NaN'))
    result=await receive(collector,(b'{invalid',json.dumps(bad).encode(),frame()))
    values=[decode_observation(raw) for raw,_ in sink.rows]
    assert [value['kind'] for value in values]==['frame','gap_observation','frame','gap_observation','frame','validated','disconnect']
    assert len(result['batches'])==1 and result['metrics']['gap_open'] is True
    assert result['metrics']['publication']=='LOCAL_UNATTESTED'

@pytest.mark.asyncio
async def test_cancelled_validation_retains_first_raw_and_latches_one_shot():
    sink=Sink();original=sink.store_capture;count=0
    async def cancel_second(**kwargs):
        nonlocal count
        count+=1
        if count==2:raise asyncio.CancelledError()
        return await original(**kwargs)
    sink.store_capture=cancel_second;collector,_,calls=make(sink)
    with pytest.raises(asyncio.CancelledError):await receive(collector,(frame(),))
    assert len(sink.rows)==1 and collector.raw_capture_failure=='SYNTHETIC_CAPTURE_UNCERTAIN'
    with pytest.raises(RuntimeError):await receive(collector,(frame(),))
    assert len(calls)==1

@pytest.mark.asyncio
async def test_unknown_store_outcome_is_terminal_without_recreation():
    collector,sink,calls=make(Sink(fail_at=2))
    with pytest.raises(RawCaptureError):await receive(collector,(frame(),))
    assert collector.raw_capture_failure=='SYNTHETIC_CAPTURE_UNCERTAIN'
    with pytest.raises(RuntimeError):await receive(collector,(frame(),))
    assert len(calls)==1
