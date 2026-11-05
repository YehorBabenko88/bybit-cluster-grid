"""Synthetic-only contract tests; no database connections or market qualification."""
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from grid.lab_observation_export import export_records, read_postgres, ExportBlocked


def request(**kwargs):
    return dict(symbol='BTCUSDT', start_ms=0, end_ms=2000, as_of_ms=3000,
                max_age_ms=1000, **kwargs)


def row(kind='derivatives_ticker', **changes):
    out=dict(id=1, symbol='BTCUSDT', event_type=kind, source='bybit',
             event_ts=datetime(1970,1,1,0,0,1,123456,tzinfo=timezone.utc),
             ingest_ts=datetime(1970,1,1,0,0,1,654321,tzinfo=timezone.utc),
             payload={'last_price':'100','bid1_price':None,'_quality':None})
    out.update(changes)
    return out


def test_preserves_clock_and_unknown_merged_quote_freshness():
    got=export_records([row()],request())
    r=got['rows'][0]
    assert r['event_ts']=='1970-01-01T00:00:01.123456+00:00'
    assert r['ingest_ts']=='1970-01-01T00:00:01.654321+00:00'
    assert r['payload']['last_price']=='100'
    assert r['payload']['bid1_price'] is None
    assert 'ask1_price' not in r['payload']
    assert r['field_freshness']=='unknown'
    assert r['event_age_ms']==1876.544
    assert r['observation_status']=='stale'
    assert got['evidence_class']=='persisted_observation_unverified'
    assert got['trading_authorized'] is False
    assert got['row_count']==1


def test_orderbook_metadata_quality_preserved_without_authentication():
    payload=dict(best_bid=100, best_ask=None,sequence=22,update_id=11,cts=999,
        _quality={'symbol':'BTCUSDT','feeds':{'orderbook':{'status':'available','reason':None}},
                  'missing_counts':{'orderbook':0},'last_update':{'orderbook':1.25}})
    r=export_records([row('orderbook_snapshot',payload=payload)],request())['rows'][0]
    expected=dict(payload, _quality={'symbol':'BTCUSDT','feeds':{'orderbook':{'status':'available'}},
        'missing_counts':{'orderbook':0},'last_update':{'orderbook':1.25}})
    assert r['payload']==expected
    assert r['source']=='bybit'
    assert r['field_freshness']=='unknown'


@pytest.mark.parametrize('bad',[dict(symbol='SUIUSDT'),dict(start_ms=True),dict(end_ms=3600001),
    dict(as_of_ms=-1),dict(max_age_ms=0),dict(sql='select 1')])
def test_invalid_request_closed(bad):
    q=request();q.update(bad)
    with pytest.raises(ExportBlocked):export_records([],q)


@pytest.mark.parametrize('rows',[ [row()]*1001, [row(payload={'last_price':{'secret':'x'}})],
    [row(payload={'last_price':'x'*1048577})], [row(event_ts=datetime(1970,1,1))],
    [row(id=2),row(id=1)], [row(event_type='trade')], [row(event_ts=datetime.fromtimestamp(2,timezone.utc))]])
def test_rejects_unsafe_or_out_of_contract_data(rows):
    with pytest.raises(ExportBlocked):export_records(rows,request())


def test_does_not_export_unknown_payload_fields():
    got=export_records([row(payload={'last_price':'1','api_key':'do not emit'})],request())
    assert got['rows'][0]['payload']=={'last_price':'1'}


class Connection:
    def __init__(self,rows=(),active=False):
        self.info=SimpleNamespace(transaction_status=int(active));self.rows=rows;self.calls=[];self.owned=False
    @contextmanager
    def transaction(self):
        self.owned=True
        try:yield
        finally:self.owned=False
    @contextmanager
    def cursor(self):yield self
    def execute(self,sql,params=None):
        assert self.owned
        self.calls.append((sql,params))
    def fetchall(self):return self.rows


def test_reader_requires_fresh_connection_and_parameterizes_half_open_range():
    active=Connection(active=True)
    with pytest.raises(ExportBlocked):read_postgres(active,request())
    assert active.calls==[]
    c=Connection()
    got=read_postgres(c,request())
    assert got['row_count']==0
    sql,params=c.calls[-1]
    assert 'event_ts>=' in sql and 'event_ts<' in sql
    assert 'ORDER BY event_ts,id' in sql
    assert 'octet_length' in sql and 'LIMIT' in sql
    assert params[1]=='BTCUSDT'
    assert any('READ ONLY' in s for s,p in c.calls)
    assert any('statement_timeout' in s for s,p in c.calls)
    assert not c.owned


def test_reader_sql_budget_and_driver_errors_are_typed_and_sanitized():
    with pytest.raises(ExportBlocked,match='BLOCKED_BYTE_LIMIT'):
        read_postgres(Connection([(None,)]),request())
    class Broken(Connection):
        def fetchall(self):raise RuntimeError('credential=SECRET')
    with pytest.raises(ExportBlocked,match='^BLOCKED_SOURCE_READ$'):
        read_postgres(Broken(),request())


def test_future_and_boundary_age_are_observations_not_field_freshness():
    q=request(); q['as_of_ms']=1123
    got=export_records([row()],q)['rows'][0]
    assert got['observation_status']=='future'
    assert got['field_freshness']=='unknown'
    q['as_of_ms']=2123
    assert export_records([row()],q)['rows'][0]['observation_status']=='observed'


def test_quality_freeform_and_unknown_keys_never_exported():
    raw=row(payload={'_quality':{'symbol':'BTCUSDT','feeds':{
        'ticker':{'status':'stale','reason':'credential=SECRET','secret':'SECRET'},
        'untrusted':{'status':'available','reason':'SECRET'}}}, 'token':'SECRET'})
    result=export_records([raw],request())
    assert result['rows'][0]['payload']=={'_quality':{'symbol':'BTCUSDT',
        'feeds':{'ticker':{'status':'stale'}}}}
    assert 'SECRET' not in str(result)


def test_client_total_byte_budget_and_deadline(monkeypatch):
    import grid.lab_observation_export as module
    monkeypatch.setattr(module,'MAX_BYTES',100)
    with pytest.raises(ExportBlocked,match='BLOCKED_BYTE_LIMIT'):
        export_records([row()],request())
    monkeypatch.setattr(module,'MAX_BYTES',8388608)
    ticks=iter([0,6])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    with pytest.raises(ExportBlocked,match='BLOCKED_DEADLINE'):
        export_records([row()],request())


def test_reader_row_sentinel_fails_no_partial_export():
    with pytest.raises(ExportBlocked,match='BLOCKED_ROW_LIMIT'):
        read_postgres(Connection([(None,)]*1001),request())


def test_invalid_nested_request_and_quality_are_typed():
    q=request();q['symbol']=[]
    with pytest.raises(ExportBlocked):export_records([],q)
    with pytest.raises(ExportBlocked):
        export_records([row(payload={'_quality':{'feeds':{'ticker':{'status':[]}}}})],request())

def test_selection_is_explicit_without_source_coverage_claim():
    got=export_records([],request())
    assert 'complete' not in got
    assert got['output_truncated'] is False
    assert got['source_completeness']=='NOT_EVALUATED'
    assert got['selection_scope']=={'symbol':'BTCUSDT','event_types':['derivatives_ticker','orderbook_snapshot'],
        'start_ms':0,'end_ms':2000,'range':'start_ms <= event_ts < end_ms',
        'ordering':['event_ts','id']}


@pytest.mark.parametrize('case',['invalid_date','cycle','deep','huge_int'])
def test_malformed_source_fails_with_sanitized_typed_error(case):
    raw=row()
    if case=='invalid_date':raw['event_ts']='SECRET invalid date'
    if case=='cycle':
        payload={};payload['loop']=payload;raw['payload']=payload
    if case=='deep':
        payload={};nested=payload
        for _ in range(1100):nested['deep']={};nested=nested['deep']
        raw['payload']=payload
    if case=='huge_int':raw['payload']={'_quality':{'last_update':{'ticker':10**10000}}}
    with pytest.raises(ExportBlocked) as caught:export_records([raw],request())
    assert str(caught.value).startswith('BLOCKED_')
    assert 'SECRET' not in str(caught.value)
    assert caught.value.__suppress_context__


def test_sql_checks_transport_record_overhead_in_addition_to_payload():
    c=Connection();read_postgres(c,request())
    sql=c.calls[-1][0]
    assert 'sum(octet_length(record::text)) OVER()<=8388608' in sql
    assert 'max(octet_length(record::text)) OVER()<=1048576' in sql
