"""Custody/schema/resource tests only; quantitative SDK acceptance remains pending."""
import json,tracemalloc
from types import SimpleNamespace
import pytest
from market_data import paper_inputs as module

@pytest.mark.parametrize('bad',[1,True,'01','+1','-1','1.0','253402300800000000','١'])
def test_microsecond_wire_is_canonical_bounded_ascii_text(bad):
    with pytest.raises(module.ExportBlocked):module._microseconds(bad)

def test_microsecond_text_roundtrip_exceeds_js_safe_integer_without_loss():
    assert module._microseconds('253402300799999999')==253402300799999999

@pytest.mark.parametrize('value',[{'a':['x','é','😀','\n',True,None,1,1.25]},[],{},'quoted"\\'])
def test_byte_accounting_matches_canonical_json(value):
    assert module._bytes(value)==len(json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode())

def test_huge_leaf_refuses_before_proportional_json_allocation():
    value='x'*9000000
    tracemalloc.start()
    try:
        with pytest.raises(module.ExportBlocked,match='BYTE_LIMIT'):module._bytes({'unexported':value})
        _,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert peak<262144


def test_empty_selection_does_not_promote_source_or_execution_authority():
    q=dict(symbol='BTCUSDT',after_id=0,start_ms=0,end_ms=1,as_of_ms=0,max_age_ms=1)
    packet=module.export_paper_inputs([],q)
    assert packet['schema']=='market_data.paper-inputs.v2' and packet['rows']==[]
    assert packet['source_authenticity']==packet['source_completeness']=='NOT_EVALUATED'
    assert packet['execution_authority'] is False and packet['trading_authorized'] is False

def test_oversized_clock_refuses_before_exception_message_allocation():
    value='x'*1000000
    tracemalloc.start()
    try:
        with pytest.raises(module.ExportBlocked,match='CLOCK'):module._timestamp(value)
        _,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert peak<262144


def test_canonical_packet_sdk_does_not_expose_unported_legacy_sql_reader():
    assert all(not hasattr(module,name) for name in ('read_paper_inputs','read_postgres','_PAPER_SQL'))

def test_canonical_nested_schemas_only_and_clock_wire_never_coerced():
    import copy
    from test_paper_inputs import rows,request,hash_value
    packet=module.export_paper_inputs(rows(),request())
    assert packet['availability_basis']=='CALLER_DECLARED_ROW_CLOCK_CUT_NOT_COMMIT_OR_PIT'
    for value in (1999000000,'01999000000','+1999000000','1999000000.0'):
        changed=copy.deepcopy(packet);changed['rows'][0]['event_us']=value
        changed['rows'][0]['row_sha256']=hash_value({k:v for k,v in changed['rows'][0].items()if k!='row_sha256'})
        with pytest.raises(module.ExportBlocked):module.validate_paper_inputs(changed)
    for schema in ('grid.lab_paper_inputs.v1','market_data.lab_paper_inputs.v1'):
        changed=copy.deepcopy(packet);changed['schema']=schema
        with pytest.raises(module.ExportBlocked):module.validate_paper_inputs(changed)
    changed=rows();changed[1]['payload']['_producer_connection']['schema']='grid.public-market-connection.v1'
    with pytest.raises(module.ExportBlocked):module.export_paper_inputs(changed,request())

def test_exact_far_epoch_microseconds_and_source_records_are_unchanged():
    import copy
    from datetime import datetime,timezone
    from test_paper_inputs import rows,request
    record=rows()[1];record['event_ts']=datetime(9999,12,31,23,59,59,998901,tzinfo=timezone.utc);record['ingest_ts']=datetime(9999,12,31,23,59,59,998999,tzinfo=timezone.utc)
    original=copy.deepcopy(record)
    q=request(start_ms=253402300799998,end_ms=253402300799999,as_of_ms=253402300799999,max_age_ms=1)
    packet=module.export_paper_inputs([record],q)
    assert packet['rows'][0]['event_us']=='253402300799998901' and packet['rows'][0]['ingest_us']=='253402300799998999'
    assert module.validate_paper_inputs(packet)==packet and record==original

def test_explicit_null_funding_stays_null_and_unavailable():
    from test_paper_inputs import row,request
    packet=module.export_paper_inputs([row(1,'derivatives_ticker',{'funding_rate':None})],request())
    assert packet['rows'][0]['payload']['funding_rate'] is None and packet['funding_status']=='UNAVAILABLE'
    assert module.paper_funding_at(packet,row_id=1,now_ms=2000001)['funding_status']=='UNAVAILABLE'

def test_exact_invalid_ohlc_cannot_pass_float_collapse_or_publish_row(monkeypatch):
    import copy
    from test_paper_inputs import row,tape,request
    payload=tape();payload.update(open='10000000000.0000000002',high='10000000000.0000000001',low='10000000000',close='10000000000.0000000001',range='0.0000000001')
    records=[row(1,'trade_tape_250ms',payload)];before=copy.deepcopy(records);hash_calls=[];original=module._paper_hash
    def observe(value):hash_calls.append(1);return original(value)
    monkeypatch.setattr(module,'_paper_hash',observe)
    with pytest.raises(module.ExportBlocked):module.export_paper_inputs(records,request())
    assert hash_calls==[] and records==before

def test_exact_positive_book_spread_survives_binary64_collapse():
    from test_paper_inputs import row,book,request
    payload=book();payload.update(best_bid='10000000000.0000000001',best_ask='10000000000.0000000002')
    packet=module.export_paper_inputs([row(1,'orderbook_snapshot',payload)],request())
    assert packet['rows'][0]['payload']['best_bid']=='10000000000.0000000001'
    assert packet['rows'][0]['payload']['best_ask']=='10000000000.0000000002'
