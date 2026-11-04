"""Synthetic rows and fresh fake transactions; no market or source qualification."""
import copy,hashlib,json
from datetime import datetime,timezone
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from grid.lab_observation_export import export_paper_inputs,read_paper_inputs,validate_paper_inputs,ExportBlocked

def stamp(ms):return datetime.fromtimestamp(ms/1000,timezone.utc)
def hash_value(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
def request(**changes):
 q=dict(symbol='BTCUSDT',after_id=0,start_ms=1990000,end_ms=2000001,as_of_ms=2000000,max_age_ms=10000);q.update(changes);return q
def context(identity='a'*32,category='linear'):
 return dict(schema='grid.public-market-connection.v1',venue='bybit',category=category,endpoint='wss://stream.bybit.com/v5/public/'+category,connection_id=identity,scope='PRODUCER_DECLARED_LOCAL_CONNECTION_NOT_REMOTE_AUTHENTICATION')
def row(index,kind,payload,event=1999000,ingest=1999500):
 payload=copy.deepcopy(payload);payload['_producer_connection']=context('b'*32 if kind=='trade_tape_250ms'else'a'*32)
 return dict(id=index,symbol='BTCUSDT',source='bybit',event_type=kind,payload=payload,event_ts=stamp(event),ingest_ts=stamp(ingest))
def tape():return dict(start_ms=1999000,open=100,high=102,low=99,close=101,buy_volume=2,sell_volume=1,buy_count=2,sell_count=1,trade_count=3,delta=1,cvd=5,range=3,aggressor_imbalance=1/3)
def book(seq=10,update=20):return dict(best_bid='100',best_ask='101',sequence=seq,update_id=update,cts=1999500,_quality={'symbol':'BTCUSDT','feeds':{'orderbook':{'status':'available','reason':'omitted free text'}}})
def funding(proof=True):
 p=dict(funding_rate='0.0001',funding_interval_hour='8',next_funding_time='28800000')
 if proof:p['_field_observations']={'schema':'grid.ticker-field-observations.v1','clock_basis':'EXCHANGE_FRAME_TS_AND_PROCESS_WALL_CLOCK','fields':{k:dict(event_ms=1999800,observed_ms=1999850,value_sha256=hash_value(v))for k,v in p.items()}}
 return p
def rows():return [row(1,'trade_tape_250ms',tape()),row(2,'orderbook_snapshot',book(),1999600,1999700),row(3,'derivatives_ticker',funding(),1999800,1999900)]

def test_real_kinds_exact_clocks_hashes_and_unattested_qualifiers():
 raw=rows();raw[0]['payload']['private_unexported']='secret'
 packet=export_paper_inputs(raw,request());assert packet['schema']=='grid.lab_paper_inputs.v1'
 assert packet['cursor']==3 and packet['funding_status']=='KNOWN_SOURCE_FIELDS'
 assert packet['source_authenticity']=='NOT_EVALUATED'and packet['source_completeness']=='NOT_EVALUATED'
 assert packet['trading_authorized'] is False and packet['execution_authority'] is False
 first=packet['rows'][0];assert first['event_us']==1999000000 and first['ingest_us']==1999500000
 assert first['payload_sha256']==hash_value(raw[0]['payload']);assert 'private_unexported'not in first['payload']
 assert first['row_sha256']==hash_value({k:v for k,v in first.items()if k!='row_sha256'})
 assert validate_paper_inputs(packet)==packet

@pytest.mark.parametrize('change',[{'symbol':'SUIUSDT'},{'after_id':True},{'start_ms':2000001},{'end_ms':6000001},{'max_age_ms':0},{'password':'secret'}])
def test_closed_request(change):
 with pytest.raises(ExportBlocked):export_paper_inputs([],request(**change))

@pytest.mark.parametrize('mutate',[
 lambda r:r[0].update(event_type='derivatives_ticker'),
 lambda r:r[0]['payload'].update(start_ms=1999001),
 lambda r:r[0].update(ingest_ts=stamp(1999100)),
 lambda r:r[1]['payload'].update(best_ask='99'),
 lambda r:r[1]['payload'].update(sequence=True),
 lambda r:r[1]['payload']['_quality']['feeds']['orderbook'].update(status='missing'),
 lambda r:r[2]['payload']['_field_observations']['fields']['funding_rate'].update(value_sha256='a'*64),
 lambda r:r[2]['payload']['_field_observations']['fields']['funding_rate'].update(event_ms=2000001),
 lambda r:r[0].update(id=0),
])
def test_invalid_inputs_block_whole_packet(mutate):
 records=rows();mutate(records)
 with pytest.raises(ExportBlocked):export_paper_inputs(records,request())

def test_old_funding_and_unchanged_stale_field_remain_unavailable():
 records=rows();records[2]['payload']=funding(False)
 assert export_paper_inputs(records,request())['funding_status']=='UNAVAILABLE'
 records=rows();records[2]['payload']['_field_observations']['fields']['funding_interval_hour'].update(event_ms=1900000,observed_ms=1900000)
 assert export_paper_inputs(records,request())['funding_status']=='UNAVAILABLE'

def test_no_fake_epoch_no_id_contiguity_or_sequence_jump_requirement():
 records=[row(5,'orderbook_snapshot',book(10,20),1999000,1999500),row(99,'orderbook_snapshot',book(999,888),1999600,1999700)]
 packet=export_paper_inputs(records,request());assert packet['cursor']==99
 assert 'epoch'not in packet['rows'][0]
 records[1]['payload']['sequence']=9
 with pytest.raises(ExportBlocked):export_paper_inputs(records,request())

def test_packet_tamper_or_qualification_upgrade_rejected():
 packet=export_paper_inputs(rows(),request())
 for change in ({'source_authenticity':'VERIFIED'},{'execution_authority':True},{'cursor':4}):
  bad=copy.deepcopy(packet);bad.update(change)
  with pytest.raises(ExportBlocked):validate_paper_inputs(bad)
 bad=copy.deepcopy(packet);bad['rows'][1]['payload']['best_bid']='5'
 with pytest.raises(ExportBlocked):validate_paper_inputs(bad)

class Connection:
 def __init__(self,records=(),active=0):self.info=SimpleNamespace(transaction_status=active);self.records=records;self.calls=[];self.in_tx=False
 @contextmanager
 def transaction(self):
  self.in_tx=True
  try:yield
  finally:self.in_tx=False
 @contextmanager
 def cursor(self):yield self
 def execute(self,sql,args=None):assert self.in_tx;self.calls.append((sql,args))
 def fetchall(self):return self.records

def test_reader_fixed_sql_readonly_and_no_partial_budget_success():
 conn=Connection([(r,)for r in rows()]);packet=read_paper_inputs(conn,request());assert packet['cursor']==3
 sql,args=conn.calls[-1];assert 'id>%s'in sql and 'ORDER BY id'in sql and 'LIMIT'in sql
 assert args[0]=='BTCUSDT'and args[1]==0
 assert any('REPEATABLE READ READ ONLY'in s for s,_ in conn.calls)
 assert any('statement_timeout'in s for s,_ in conn.calls)
 assert not conn.in_tx
 for conn in (Connection(active=1),Connection([(None,)]),Connection([(rows()[0],)]*1001)):
  with pytest.raises(ExportBlocked):read_paper_inputs(conn,request())


@pytest.mark.parametrize('kind',[[],{},None,True])
def test_serialized_packet_bad_kind_is_typed_unavailable(kind):
 packet=export_paper_inputs(rows(),request());packet['rows'][0]['event_type']=kind
 packet['rows'][0]['row_sha256']=hash_value({k:v for k,v in packet['rows'][0].items()if k!='row_sha256'})
 with pytest.raises(ExportBlocked):validate_paper_inputs(packet)


def test_pure_export_enforces_aggregate_raw_budget_before_projection():
 records=[]
 for i in range(10):
  payload=book(100+i,200+i);payload['unexported']='X'*900000
  records.append(row(i+1,'orderbook_snapshot',payload,1999000+i,1999500+i))
 with pytest.raises(ExportBlocked,match='BYTE_LIMIT'):export_paper_inputs(records,request())


def test_last_row_work_cannot_succeed_after_whole_validation_deadline(monkeypatch):
 from grid import lab_observation_export as module
 packet=export_paper_inputs([rows()[1]],request());clock=[0.];original=module._paper_hash
 monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
 def slow_hash(value):
  result=original(value);clock[0]=6.;return result
 monkeypatch.setattr(module,'_paper_hash',slow_hash)
 with pytest.raises(ExportBlocked,match='DEADLINE'):validate_paper_inputs(packet)

def test_reader_checks_whole_budget_after_transform(monkeypatch):
 from grid import lab_observation_export as module
 packet=export_paper_inputs(rows(),request());clock=[0.]
 monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
 def slow_transform(*args):clock[0]=6.;return packet
 monkeypatch.setattr(module,'export_paper_inputs',slow_transform)
 with pytest.raises(ExportBlocked,match='DEADLINE'):read_paper_inputs(Connection(),request())


# Reuse the independently guarded hosted-only PG18 private-schema fixture.
# Import performs no connection; its guard precedes psycopg import/connect.
from test_lab_observation_export_postgres import database,_insert,_snapshot

def _insert_paper_fixture(writer,symbol,kind,payload,event,ingest):
 payload=copy.deepcopy(payload);payload['_producer_connection']=context('b'*32 if kind=='trade_tape_250ms'else'a'*32)
 identity=_insert(writer,symbol,ms=event,kind=kind,payload=payload)
 writer.execute('UPDATE market_events SET ingest_ts=%s WHERE id=%s',(stamp(ingest),identity))
 return identity

def test_actual_hosted_pg18_ten_symbol_source_projection_without_mutation(database):
 from grid.lab_observation_export import SYMBOLS
 writer,connect=database
 expected={}
 for symbol in sorted(SYMBOLS):
  items=[('trade_tape_250ms',tape(),1999000,1999500),('orderbook_snapshot',book(),1999600,1999700),('derivatives_ticker',funding(),1999800,1999900)]
  expected[symbol]=[_insert_paper_fixture(writer,symbol,*item)for item in items]
 before=_snapshot(writer);reader=connect()
 for symbol in sorted(SYMBOLS):
  packet=read_paper_inputs(reader,request(symbol=symbol))
  assert [r['id']for r in packet['rows']]==expected[symbol]
  assert packet['cursor']==expected[symbol][-1] and packet['funding_status']=='KNOWN_SOURCE_FIELDS'
  assert validate_paper_inputs(packet)==packet and reader.info.transaction_status==0
 assert _snapshot(writer)==before

def test_actual_hosted_pg18_later_ingest_blocks_without_skipping_cursor(database):
 writer,connect=database
 first=_insert_paper_fixture(writer,'BTCUSDT','orderbook_snapshot',book(),1999000,1999500)
 reader=connect();prior=read_paper_inputs(reader,request());assert prior['cursor']==first
 second=_insert_paper_fixture(writer,'BTCUSDT','orderbook_snapshot',book(11,21),1999600,2000001)
 deferred=read_paper_inputs(reader,request(after_id=first))
 assert deferred['rows']==[] and deferred['cursor']==first
 assert deferred['availability']['state']=='UNAVAILABLE' and deferred['availability']['cut_before_id']==second
 assert prior['cursor']==first and reader.info.transaction_status==0
 next_packet=read_paper_inputs(reader,request(after_id=first,as_of_ms=2000002))
 assert [r['id']for r in next_packet['rows']]==[second] and next_packet['cursor']==second


def test_future_ingest_cuts_visible_id_prefix_without_skipping_later_id():
 records=[row(5,'orderbook_snapshot',book(9,19),1999000,1999500),row(10,'orderbook_snapshot',book(10,20),1999600,2000001),row(11,'orderbook_snapshot',book(11,21),1999700,1999900)]
 packet=export_paper_inputs(records,request())
 assert [r['id']for r in packet['rows']]==[5] and packet['cursor']==5
 assert packet['output_truncated'] is True
 assert packet['availability']=={'mode':'VISIBLE_ID_PREFIX','as_of_ms':2000000,'cut_before_id':10,'state':'PARTIAL','scope':'SELECTED_VISIBLE_ROWS_NOT_STREAM_COMPLETENESS'}
 assert validate_paper_inputs(packet)==packet
 replay=export_paper_inputs(records[1:],request(after_id=5,as_of_ms=2000002))
 assert [r['id']for r in replay['rows']]==[10,11] and replay['cursor']==11
 assert replay['output_truncated'] is False and replay['availability']['state']=='AVAILABLE'

def test_first_future_ingest_holds_cursor_and_never_emits_later_rows():
 records=[row(10,'orderbook_snapshot',book(10,20),1999600,2000001),row(11,'orderbook_snapshot',book(11,21),1999700,1999900)]
 packet=export_paper_inputs(records,request(after_id=5))
 assert packet['rows']==[] and packet['cursor']==5 and packet['availability']['state']=='UNAVAILABLE'
 assert packet['availability']['cut_before_id']==10 and packet['output_truncated'] is True

def test_future_exchange_clock_is_not_relabelled_as_availability_prefix():
 with pytest.raises(ExportBlocked,match='CLOCK'):export_paper_inputs([row(10,'orderbook_snapshot',book(),2000001,2000002)],request(end_ms=2000003))


def test_legacy_unmarked_or_changed_connection_facts_never_enable_paper():
 records=rows()
 for item in records:item['payload'].pop('_producer_connection')
 packet=export_paper_inputs(records,request())
 assert packet['producer_context_status']=='UNAVAILABLE' and packet['funding_status']=='UNAVAILABLE'
 forged=copy.deepcopy(packet);forged['producer_context_status']='CONSISTENT';forged['funding_status']='KNOWN_SOURCE_FIELDS'
 with pytest.raises(ExportBlocked):validate_paper_inputs(forged)
 records=rows();records[2]['payload']['_producer_connection']=context('c'*32)
 packet=export_paper_inputs(records,request())
 assert packet['producer_context_status']=='UNAVAILABLE' and packet['funding_status']=='UNAVAILABLE'
 records=[row(1,'orderbook_snapshot',book(1,2),1999000,1999500),row(2,'orderbook_snapshot',book(2,3),1999600,1999700)]
 records[1]['payload']['_producer_connection']=context('c'*32)
 assert export_paper_inputs(records,request())['producer_context_status']=='UNAVAILABLE'

def test_separate_tape_connection_allowed_but_wrong_category_or_endpoint_rejected():
 packet=export_paper_inputs(rows(),request());assert packet['producer_context_status']=='CONSISTENT'
 assert packet['rows'][0]['payload']['_producer_connection']['connection_id']!=packet['rows'][1]['payload']['_producer_connection']['connection_id']
 for mutation in ({'category':'spot','endpoint':'wss://stream.bybit.com/v5/public/spot'},{'endpoint':'wss://evil.example/linear'},{'scope':'REMOTE_AUTHENTICATED'}):
  records=rows();records[0]['payload']['_producer_connection'].update(mutation)
  with pytest.raises(ExportBlocked):export_paper_inputs(records,request())


def test_funding_use_time_assessment_preserves_original_selection_and_cut():
 from grid.lab_observation_export import paper_funding_at
 records=rows()+[row(10,'orderbook_snapshot',book(11,21),1999900,2000001)]
 packet=export_paper_inputs(records,request());before=copy.deepcopy(packet)
 result=paper_funding_at(packet,row_id=3,now_ms=2000001)
 assert result==dict(funding_status='KNOWN_SOURCE_FIELDS',evaluated_at_ms=2000001,source_request_sha256=hash_value(packet['request']),row_sha256=packet['rows'][-1]['row_sha256'])
 assert packet==before and packet['availability']['cut_before_id']==10
 # Only the chosen funding fields age at use-time; old tape rows are not
 # rewritten as a newly queried complete/current packet.
 assert paper_funding_at(packet,row_id=3,now_ms=2009800)['funding_status']=='KNOWN_SOURCE_FIELDS'
 assert paper_funding_at(packet,row_id=3,now_ms=2009801)['funding_status']=='UNAVAILABLE'

@pytest.mark.parametrize('row_id,now',[(1,2000001),(3,1999999),(True,2000001),(3,True)])
def test_funding_assessment_rejects_wrong_row_replay_or_bad_clock(row_id,now):
 from grid.lab_observation_export import paper_funding_at
 with pytest.raises(ExportBlocked):paper_funding_at(export_paper_inputs(rows(),request()),row_id=row_id,now_ms=now)

def test_funding_assessment_never_upgrades_unknown_or_selects_prior_ticker():
 from grid.lab_observation_export import paper_funding_at
 records=rows();records[-1]['payload'].pop('_field_observations')
 packet=export_paper_inputs(records,request())
 assert paper_funding_at(packet,row_id=3,now_ms=2000001)['funding_status']=='UNAVAILABLE'
 records=rows()+[row(4,'derivatives_ticker',funding(),1999900,1999950)]
 packet=export_paper_inputs(records,request())
 with pytest.raises(ExportBlocked):paper_funding_at(packet,row_id=3,now_ms=2000001)
 assert paper_funding_at(packet,row_id=4,now_ms=2000001)['funding_status']=='KNOWN_SOURCE_FIELDS'
