"""Exact raw DTO and durable consumer-ACK contracts; inert transport only."""
import asyncio
from decimal import Decimal, localcontext
import json
import pytest
from market_data.public_trades import Trade, parse_trades
from market_data.collector import PublicTradeCollector
from market_data.raw_capture import RawCaptureError, decode_observation
from test_capture_runtime import Sink, Frames, ACK

def frame(*rows):
    return json.dumps({'topic':'publicTrade.BTCUSDT','data':list(rows)})
def row(identity='one',**overrides):
    return dict(dict(s='BTCUSDT',T=1000,p='0.1',v='1e-1000',S='Buy',i=identity),**overrides)
def parse(*rows,now=2000):return parse_trades(json.loads(frame(*rows)),'BTCUSDT',now)

def test_one_frozen_decimal_dto_preserves_exact_and_tiny_values():
    trade,=parse(row())
    assert type(trade.price) is Decimal and trade.price==Decimal('0.1')
    assert type(trade.qty) is Decimal and trade.qty==Decimal('1e-1000') and trade.qty!=0
    with pytest.raises(Exception):trade.qty=Decimal(0)

@pytest.mark.parametrize('stamp',[True,'1000',1000.0,0,-1,2**63])
def test_provider_timestamp_is_strict_bounded_integer(stamp):
    with pytest.raises(ValueError):parse(row(T=stamp))

@pytest.mark.parametrize('values',[{'p':0.1},{'v':1.0},{'p':'NaN'},{'v':'0'},{'v':'1'*161}])
def test_provider_numeric_fields_are_bounded_exact_text(values):
    with pytest.raises(ValueError):parse(row(**values))

def test_clock_admission_and_decimal_context_do_not_round():
    for clock in (True,'2000',2000.0,-1,2**63):
        with pytest.raises(ValueError):parse(row(v='1'),now=clock)
    with localcontext() as context:
        context.prec=2
        for signal in context.traps:context.traps[signal]=True
        trade,=parse(row(p='12345.67890000000000001'))
        assert str(trade.price)=='12345.67890000000000001' and str(trade.qty)=='1E-1000'
        assert not any(context.flags.values())

class Consumer:
    def __init__(self):self.records={};self.calls=[];self.fail_after_commit=None
    async def __call__(self,trade,*,delivery_key,content_sha256):
        self.calls.append(trade.trade_id)
        assert len(delivery_key)==len(content_sha256)==64
        prior=self.records.setdefault(delivery_key,content_sha256)
        assert prior==content_sha256
        if trade.trade_id==self.fail_after_commit:raise OSError('unknown synthetic commit outcome')
        return dict(delivery_key=delivery_key,content_sha256=content_sha256,committed=True)

async def run_frames(rows,consumer,sink=None):
    sink=sink or Sink();connections=[]
    async def connector(endpoint):connections.append(endpoint);return Frames(rows)
    collector=PublicTradeCollector(sink,symbol='BTCUSDT',source_revision='a'*40,connector=connector,clock_ms=lambda:2000,max_frames=len(rows),on_execution=consumer)
    result=await collector.run()
    return result,sink,connections

@pytest.mark.asyncio
async def test_dedup_only_after_raw_validation_and_durable_ack():
    sink=Sink();consumer=Consumer()
    async def acknowledge(trade,**identity):
        kinds=[decode_observation(raw)['kind'] for raw,_ in sink.rows]
        assert kinds[-1]=='validated'
        assert trade.qty==Decimal('1e-1000')
        return await consumer(trade,**identity)
    result,_,connections=await run_frames([ACK,frame(row(),row()),frame(row())],acknowledge,sink)
    assert consumer.calls==['one'] and len(consumer.records)==1
    assert result['accepted_trade_observations']==3 and result['acknowledged_unique_executions']==1
    assert result['source_authenticity']=='NOT_INDEPENDENTLY_VERIFIED' and len(connections)==1

@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[row('two',p='NaN'),row('one',v='2')])
async def test_partial_or_conflicting_batch_has_no_consumer_effect(bad):
    consumer=Consumer();sink=Sink()
    with pytest.raises(ValueError):await run_frames([ACK,frame(row(),bad)],consumer,sink)
    assert consumer.calls==[] and consumer.records=={}
    assert 'validated' not in [decode_observation(raw)['kind'] for raw,_ in sink.rows]

@pytest.mark.asyncio
async def test_missing_or_mismatched_literal_commit_ack_never_succeeds():
    for answer in (None,True,{'committed':True},{'delivery_key':'0'*64,'content_sha256':'0'*64,'committed':True}):
        calls=[]
        async def refuse(trade,**identity):calls.append(trade.trade_id);return answer
        with pytest.raises(RawCaptureError):await run_frames([ACK,frame(row())],refuse)
        assert calls==['one']

@pytest.mark.asyncio
async def test_explicit_recovery_uses_same_event_keys_without_duplicate_effect():
    consumer=Consumer();consumer.fail_after_commit='two'
    original=frame(row('one'),row('two'))
    with pytest.raises(RawCaptureError):await run_frames([ACK,original],consumer)
    assert len(consumer.records)==2 and consumer.calls==['one','two']
    before=dict(consumer.records);consumer.fail_after_commit=None
    result,_,_=await run_frames([ACK,original,original],consumer)
    assert consumer.records==before and consumer.calls==['one','two','one','two']
    assert result['acknowledged_unique_executions']==2

@pytest.mark.asyncio
async def test_source_write_refusal_prevents_all_delivery():
    consumer=Consumer()
    with pytest.raises(RawCaptureError):await run_frames([ACK,frame(row())],consumer,Sink(fail_at=3))
    assert consumer.calls==[]


def test_invalid_exponent_parse_preserves_caller_decimal_flags():
    with localcontext() as context:
        context.prec=2
        for signal in context.traps:context.traps[signal]=True
        with pytest.raises(ValueError):parse(row(p='1e999999999999999999999999999999999'))
        assert not any(context.flags.values())

def test_same_exact_semantics_have_same_recovery_content_digest():
    from market_data.public_trades import delivery_identity
    first,=parse(row(p='0.1',v='1e-1000'))
    second,=parse(row(p='0.1000',v='10e-1001'))
    assert delivery_identity(first)==delivery_identity(second)
    with pytest.raises(ValueError):Trade('BTCUSDT',1000,0.1,Decimal(1),'Buy','one')

@pytest.mark.asyncio
async def test_conflicting_acknowledged_id_refuses_whole_later_batch():
    consumer=Consumer()
    with pytest.raises(ValueError):await run_frames([ACK,frame(row()),frame(row('new'),row(v='2'))],consumer)
    assert consumer.calls==['one'] and len(consumer.records)==1

@pytest.mark.asyncio
async def test_nonliteral_commit_boolean_refused_without_dedup():
    calls=[]
    async def ambiguous(trade,**identity):calls.append(trade.trade_id);return dict(identity,committed=1)
    with pytest.raises(RawCaptureError):await run_frames([ACK,frame(row())],ambiguous)
    assert calls==['one']
