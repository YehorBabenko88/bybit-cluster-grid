import asyncio,importlib.util,json,hashlib
import pytest
from market_data.segment_wal import SegmentWAL
from test_capture_runtime import Sink

def module():
    assert importlib.util.find_spec('market_data.ticker_acquisition') is not None,'canonical ticker acquisition is missing'
    from market_data import ticker_acquisition
    return ticker_acquisition

def frame(ts,data,kind='delta'):
    return json.dumps(dict(topic='tickers.BTCUSDT',type=kind,ts=ts,data=data))

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def test_original_field_clocks_omission_same_value_null_and_reconnect():
    m=module();s=m.TickerState('BTCUSDT');s.begin_epoch('00000000-0000-4000-8000-000000000001')
    first=s.prepare(dict(topic='tickers.BTCUSDT',type='snapshot',ts=1999000,data=dict(fundingRate='0.0001',nextFundingTime='28800000')),2000000)
    s.commit(first);proof=s.snapshot()['field_observations']['fields']
    s.commit(s.prepare(dict(topic='tickers.BTCUSDT',type='delta',ts=1999500,data=dict(lastPrice='100')),2000000))
    assert s.snapshot()['field_observations']['fields']==proof
    s.commit(s.prepare(dict(topic='tickers.BTCUSDT',type='delta',ts=1999800,data=dict(fundingRate='0.0001')),2000000))
    assert s.snapshot()['field_observations']['fields']['funding_rate']==dict(event_ms=1999800,observed_ms=2000000,value_sha256=digest('0.0001'))
    assert s.snapshot()['field_observations']['fields']['next_funding_time']==proof['next_funding_time']
    s.commit(s.prepare(dict(topic='tickers.BTCUSDT',type='delta',ts=1999900,data=dict(fundingRate=None)),2000000))
    assert s.snapshot()['values']['funding_rate'] is None and 'funding_rate' not in s.snapshot()['field_observations']['fields']
    s.begin_epoch('00000000-0000-4000-8000-000000000002')
    assert s.snapshot()['values']=={} and s.snapshot()['fresh_snapshot'] is False

@pytest.mark.parametrize('bad',[True,'1e999',{},'NaN','-1.0000000001'])
def test_bad_funding_has_no_partial_state_mutation(bad):
    m=module();s=m.TickerState('BTCUSDT');s.begin_epoch('00000000-0000-4000-8000-000000000001');before=s.snapshot()
    with pytest.raises(ValueError):s.prepare(dict(topic='tickers.BTCUSDT',type='snapshot',ts=10,data=dict(lastPrice='1',fundingRate=bad)),20)
    assert s.snapshot()==before

class Socket:
    def __init__(self,frames):self.frames=iter(frames);self.sent=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def send(self,value):self.sent.append(json.loads(value))
    async def recv(self):return next(self.frames)

def setup(tmp_path,frames,consumer=None,sink=None):
    m=module();socket=Socket(frames);wal=SegmentWAL(tmp_path/'wal');sink=sink or Sink()
    async def connector(endpoint):assert endpoint=='wss://stream.bybit.com/v5/public/linear';return socket
    seen=[]
    async def good(payload,**binding):seen.append(payload);return dict(binding,committed=True)
    c=m.TickerAcquisition(sink,wal,symbol='BTCUSDT',source_revision='a'*40,connector=connector,clock_ms=lambda:2000000,max_frames=len(frames),on_ticker=consumer or good)
    return c,wal,sink,seen,socket

@pytest.mark.asyncio
async def test_actual_raw_ack_precedes_consumer_and_state(tmp_path):
    c,wal,sink,seen,socket=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')])
    result=await c.run();assert len(seen)==1 and wal.recover()==[]
    assert c.state.snapshot()['fresh_snapshot'] is True and result['source_authenticity']=='UNKNOWN'
    assert socket.sent==[dict(op='subscribe',args=['tickers.BTCUSDT'])]
    assert len(sink.rows)>=3

@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[None,{},dict(committed=False),dict(committed=1)])
async def test_bad_ack_retains_wal_and_poisoned_state(tmp_path,bad):
    async def consumer(payload,**binding):return bad
    c,wal,sink,seen,socket=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],consumer)
    with pytest.raises(Exception):await c.run()
    assert c.failed and len(wal.recover())==3 and [p['kind'] for _,p in wal.recover()]==['raw','raw','delivery'] and c.state.snapshot()['values']=={}
    original=wal.recover();assert c.recovery_pending()==c.recovery_pending() and wal.recover()==original
    assert c.recovery_pending()[0]['recovery_mode']=='RECONCILIATION_REQUIRED'

@pytest.mark.asyncio
async def test_store_unknown_preserves_original_occurrence(tmp_path):
    class Broken(Sink):
        async def store_capture(self,**kwargs):raise RuntimeError('uncertain')
    c,wal,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT']))],sink=Broken())
    with pytest.raises(Exception):await c.run()
    assert c.failed and len(wal.recover())==1
    assert c.recovery_pending()[0]['source_revision']=='a'*40

@pytest.mark.asyncio
async def test_commit_before_ack_restart_reuses_original_bytes_and_delivery_identity(tmp_path):
    accepted={}
    async def crash(payload,**binding):accepted[binding['delivery_sha256']]=payload;raise RuntimeError('commit ACK lost')
    c,wal,sink,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],crash)
    with pytest.raises(RuntimeError):await c.run()
    originals=[(raw,payload) for raw,payload in sink.rows];bindings=[]
    async def idempotent(payload,**binding):
        assert accepted[binding['delivery_sha256']]==payload
        assert binding['recovery_mode']=='RECOVERY_UNKNOWN_NOT_FRESH'
        bindings.append(binding);return dict(binding,committed=True)
    m=module();restarted=m.TickerAcquisition(sink,wal,symbol='BTCUSDT',source_revision='a'*40,on_ticker=idempotent)
    result=await restarted.recover()
    assert result['fresh_snapshot'] is False and restarted.state.snapshot()['values']=={}
    assert wal.recover()==[] and len(bindings)==1
    assert sink.rows[-2:]==originals[-2:]

@pytest.mark.asyncio
async def test_store_commit_before_ack_recovery_has_no_new_clock_or_identity(tmp_path):
    class CommitThenFail(Sink):
        async def store_capture(self,**kwargs):
            result=await super().store_capture(**kwargs)
            raise RuntimeError('commit ACK lost')
    sink=CommitThenFail();c,wal,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT']))],sink=sink)
    with pytest.raises(Exception):await c.run()
    original=sink.rows[0];safe=Sink();m=module()
    async def unused(*args,**kwargs):raise AssertionError('raw-only recovery has no derived publication')
    restart=m.TickerAcquisition(safe,wal,symbol='BTCUSDT',source_revision='a'*40,on_ticker=unused,clock_ms=lambda:(_ for _ in ()).throw(AssertionError('NO_NEW_CLOCK')))
    await restart.recover()
    assert safe.rows==[original] and wal.recover()==[] and restart.state.snapshot()['fresh_snapshot'] is False

@pytest.mark.asyncio
@pytest.mark.parametrize('field',['source_revision','endpoint','connection_id','frame_metadata_sha256','delivery_sha256','recovery_mode'])
async def test_every_ack_binding_tamper_retains_pending(tmp_path,field):
    async def bad(payload,**binding):return dict(binding,**{field:'tampered'},committed=True)
    c,wal,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],bad)
    with pytest.raises(Exception):await c.run()
    assert len(wal.recover())==3 and c.failed and c.state.snapshot()['values']=={}

@pytest.mark.asyncio
async def test_consumer_mutation_cannot_change_committed_candidate(tmp_path):
    async def mutate(payload,**binding):payload['values']['funding_rate']='0.9';return dict(binding,committed=True)
    c,wal,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],mutate)
    await c.run();assert c.state.snapshot()['values']['funding_rate']=='0.0001'

@pytest.mark.asyncio
@pytest.mark.parametrize('frames',[ [frame(1999000,dict(fundingRate='0.0001'),'snapshot')], [json.dumps(dict(op='subscribe',success=True,args=['tickers.OTHER']))], [json.dumps(dict(op='subscribe',success=1,args=['tickers.BTCUSDT']))], [json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),'{bad'] ])
async def test_strict_subscription_invalid_frames_preserved_with_gap(tmp_path,frames):
    c,wal,sink,*_=setup(tmp_path,frames)
    with pytest.raises(ValueError):await c.run()
    from market_data.raw_capture import decode_observation
    kinds=[decode_observation(raw)['kind'] for raw,_ in sink.rows]
    assert 'frame' in kinds and 'gap_observation' in kinds and c.state.snapshot()['values']=={}

@pytest.mark.asyncio
async def test_cancelled_consumer_retains_wal_and_prevents_restart(tmp_path):
    async def cancelled(payload,**binding):raise asyncio.CancelledError
    c,wal,sink,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],cancelled)
    with pytest.raises(asyncio.CancelledError):await c.run()
    assert c.failed and len(wal.recover())==3
    m=module();fresh=m.TickerAcquisition(sink,wal,symbol='BTCUSDT',source_revision='a'*40,on_ticker=cancelled)
    with pytest.raises(Exception):await fresh.run()
    assert len(wal.recover())==3

@pytest.mark.asyncio
async def test_duplicate_frames_are_distinct_receive_occurrences(tmp_path):
    raw=frame(1999000,dict(fundingRate='0.0001'),'snapshot');keys=[]
    async def good(payload,**binding):keys.append((binding['frame_metadata_sha256'],binding['delivery_sha256']));return dict(binding,committed=True)
    c,wal,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),raw,raw],good)
    result=await c.run();assert result['accepted_observations']==2 and len({k[0] for k in keys})==2 and len({k[1] for k in keys})==2

@pytest.mark.asyncio
async def test_recovery_source_mismatch_refuses_before_any_store_or_ack(tmp_path):
    async def fail(payload,**binding):raise RuntimeError('unknown')
    c,wal,sink,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],fail)
    with pytest.raises(RuntimeError):await c.run()
    before=list(sink.rows);m=module();restart=m.TickerAcquisition(sink,wal,symbol='BTCUSDT',source_revision='b'*40,on_ticker=fail)
    with pytest.raises(ValueError):await restart.recover()
    assert sink.rows==before and len(wal.recover())==3 and restart.failed

@pytest.mark.asyncio
async def test_recovery_failed_receipt_retains_all_original_rows(tmp_path):
    async def fail(payload,**binding):raise RuntimeError('unknown')
    c,wal,sink,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],fail)
    with pytest.raises(RuntimeError):await c.run()
    original=wal.recover()
    class Corrupt(Sink):
        async def store_capture(self,**kwargs):
            facts=await super().store_capture(**kwargs);facts.observation_sha256='0'*64;return facts
    m=module();restart=m.TickerAcquisition(Corrupt(),wal,symbol='BTCUSDT',source_revision='a'*40,on_ticker=fail)
    with pytest.raises(Exception):await restart.recover()
    assert wal.recover()==original and restart.failed

def test_present_empty_unknown_and_unvalidated_nonfunding_are_explicit():
    m=module();s=m.TickerState('BTCUSDT');s.begin_epoch('00000000-0000-4000-8000-000000000001')
    s.commit(s.prepare(dict(topic='tickers.BTCUSDT',type='snapshot',ts=10,data=dict(lastPrice='not-numeric',fundingRate='')),20))
    got=s.snapshot();assert got['values']==dict(last_price='not-numeric',funding_rate=None)
    assert got['nonfunding_numeric_status']=='UNVALIDATED' and got['field_observations']['fields']=={}

@pytest.mark.asyncio
async def test_recovery_delivery_never_claims_current_fresh_snapshot(tmp_path):
    async def fail(payload,**binding):
        assert 'fresh_snapshot' not in payload and payload['original_epoch_snapshot_seen'] is True
        raise RuntimeError('unknown')
    c,wal,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],fail)
    with pytest.raises(RuntimeError):await c.run()
    assert c.state.snapshot()['fresh_snapshot'] is False

@pytest.mark.asyncio
async def test_wal_complete_prefix_ack_is_atomic_and_rejects_missing_prefix(tmp_path,monkeypatch):
    wal=SegmentWAL(tmp_path/'prefix');ids=[await wal.append(dict(n=i)) for i in range(3)]
    assert callable(getattr(wal,'ack_prefix',None)),'atomic complete-prefix ACK is missing'
    with pytest.raises(ValueError):await wal.ack_prefix(ids[1:])
    assert len(wal.recover())==3
    import market_data.segment_wal as wm
    original=wm.os.replace;seen=[]
    def fail_before_publish(source,dest):
        if str(dest).endswith('checkpoint'):seen.append(str(dest));raise OSError('checkpoint publish unknown')
        return original(source,dest)
    monkeypatch.setattr(wm.os,'replace',fail_before_publish)
    with pytest.raises(OSError):await wal.ack_prefix(ids)
    assert len(wal.recover())==3 and len(seen)==1
    monkeypatch.setattr(wm.os,'replace',original)
    await wal.ack_prefix(ids);assert wal.recover()==[]

@pytest.mark.asyncio
async def test_funding_bad_second_frame_never_publishes_partial_candidate(tmp_path):
    c,wal,sink,seen,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot'),frame(1999500,dict(lastPrice='123',fundingRate='99'))])
    with pytest.raises(ValueError):await c.run()
    assert len(seen)==1 and c.state.snapshot()['values']==dict(funding_rate='0.0001')
    assert c.state.snapshot()['fresh_snapshot'] is False

def test_backward_process_clock_removes_only_updated_field_proof():
    m=module();s=m.TickerState('BTCUSDT');s.begin_epoch('00000000-0000-4000-8000-000000000001')
    s.commit(s.prepare(dict(topic='tickers.BTCUSDT',type='snapshot',ts=1999000,data=dict(fundingRate='0.0001',nextFundingTime='28800000')),2000000))
    old=s.snapshot()['field_observations']['fields']['next_funding_time']
    s.commit(s.prepare(dict(topic='tickers.BTCUSDT',type='delta',ts=1999100,data=dict(fundingRate='0.1')),1999999))
    assert 'funding_rate' not in s.snapshot()['field_observations']['fields'] and s.snapshot()['field_observations']['fields']['next_funding_time']==old

@pytest.mark.asyncio
async def test_managed_admission_revocation_before_consumer_ack_retains_wal(tmp_path,monkeypatch):
    for key,value in dict(UNIFIED_MODULE_ID='market_data',UNIFIED_INSTANCE_TOKEN='b'*64,UNIFIED_MODULE_VERSION='fixture',UNIFIED_RELEASE_ID='fixture-release').items():monkeypatch.setenv(key,value)
    class Admission:
        current=True
        def require_current(self):return self.current
    admission=Admission()
    async def consumer(payload,**binding):admission.current=False;return dict(binding,committed=True)
    c,wal,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT'])),frame(1999000,dict(fundingRate='0.0001'),'snapshot')],consumer)
    c.startup_admission=admission
    with pytest.raises(RuntimeError):await c.run()
    assert c.failed and len(wal.recover())==3 and c.state.snapshot()['values']=={}

@pytest.mark.asyncio
async def test_revocation_during_wal_append_prevents_underlying_store(tmp_path,monkeypatch):
    for key,value in dict(UNIFIED_MODULE_ID='market_data',UNIFIED_INSTANCE_TOKEN='b'*64,UNIFIED_MODULE_VERSION='fixture',UNIFIED_RELEASE_ID='fixture-release').items():monkeypatch.setenv(key,value)
    class Admission:
        current=True
        def require_current(self):return self.current
    admission=Admission();c,wal,sink,*_=setup(tmp_path,[json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT']))])
    c.startup_admission=admission;append=wal.append
    async def revoke(payload):
        rid=await append(payload);admission.current=False;return rid
    monkeypatch.setattr(wal,'append',revoke)
    with pytest.raises(Exception):await c.run()
    assert sink.rows==[] and len(wal.recover())==1 and c.failed

@pytest.mark.asyncio
async def test_transport_cancellation_records_disconnect_when_no_outcome_is_pending(tmp_path):
    ack=json.dumps(dict(op='subscribe',success=True,args=['tickers.BTCUSDT']))
    c,wal,sink,_,socket=setup(tmp_path,[ack,ack]);count=0
    async def recv():
        nonlocal count
        count+=1
        if count==1:return ack
        raise asyncio.CancelledError
    socket.recv=recv
    with pytest.raises(asyncio.CancelledError):await c.run()
    from market_data.raw_capture import decode_observation
    last=decode_observation(sink.rows[-1][0])
    assert last['kind']=='disconnect' and last['reason']=='cancelled' and wal.recover()==[]
