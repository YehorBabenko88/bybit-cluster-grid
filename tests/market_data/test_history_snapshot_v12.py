"""Pure opt-in catalog/rollup v1.2; all receipts are synthetic declarations."""
import copy, unittest
from decimal import localcontext
from unittest.mock import patch
from market_data.footprint_state import FootprintBuilder
from market_data.public_trades import Trade
from market_data.provenance import minute_record_v12, digest
from market_data.history_export_v12 import export_records_v12
from test_turnover_history import UNITS, BASIS, source
from test_history_snapshot import Connection

def module():
 from market_data import history_snapshot_v12
 return history_snapshot_v12

def fixture(n=5, start=0, delay=False, asof=None):
 b=FootprintBuilder('.01')
 for i in range(n):b.add(Trade('BTCUSDT',start+i*60000+1000,str(200+i),'1','Buy',str(i)))
 raw=b.pop_closed(start+n*60000);records=[];receipts={}
 for i,row in enumerate(raw):
  row['source_provenance']=source();known=900000 if delay and i==2 else start+(i+1)*60000
  r=minute_record_v12(row,start+(i+1)*60000+1000,'fixture',available_at_ms=known,units=UNITS)
  records.append(r);fp=r['dataset_fingerprint']
  receipts[fp]=dict(schema='market_data.history.receipt.v1.2',record_api_version={'major':1,'minor':2},dataset_schema='market_data.dataset.v1.2',fingerprint=fp,venue='bybit',available_at_ms=known,watermark_ms=start+(i+1)*60000,complete=True,units=dict(UNITS),evidence_class='HISTORICAL',turnover_basis=BASIS)
 end=start+n*60000;asof=max(end,900000) if asof is None else asof
 q=dict(schema='market_data.history.request.v1.2',venue='bybit',market_type='linear',symbol='BTCUSDT',start_ms=start,end_ms=end,as_of_ms=asof,max_age_ms=2000000000,units=dict(UNITS))
 t=dict(schema='market_data.history.trust.v1.2',identity='fixture',source_revision='a'*40,epoch=source()['epoch'],receipts=receipts,receipt_pins={fp:digest(r) for fp,r in receipts.items()},evidence_class='HISTORICAL')
 env=export_records_v12(records,q,t)
 entry=dict(schema='market_data.history.catalog-entry.v1.2',request=q,trust=t,revisions=[r['dataset_fingerprint'] for r in records],dataset_id=env['dataset_id'],dataset_fingerprint=env['dataset_fingerprint'])
 pin=digest(entry);s=dict(schema='market_data.history.selection.v1.2',operation='minutes',snapshot_id=pin,**{k:q[k] for k in ('venue','market_type','symbol','start_ms','end_ms')})
 return records,s,{pin:entry},env

def window(s):return dict(s,operation='window',timeframe='5m')
def reseal(x):x['dataset_fingerprint']=digest({k:v for k,v in x.items() if k!='dataset_fingerprint'});return x
class SnapshotV12Tests(unittest.TestCase):
 def test_minutes_new_catalog_identity_and_actual_envelope(self):
  r,s,c,e=fixture();conn=Connection(r);self.assertEqual(module().select_snapshot_v12(conn,s,c),e)
  old=dict(next(iter(c.values())));old.pop('schema');self.assertNotEqual(digest(old),s['snapshot_id']);self.assertEqual(len(e['rows'][0]),14)
 def test_delayed_middle_actual_turnover_window_is_1010_available_900000(self):
  r,s,c,e=fixture(delay=True);x=module().rollup_snapshot_v12(e,window(s),c);row,=x['rows']
  self.assertEqual((row['turnover'],row['volume'],row['available_at_ms'],row['watermark_ms']),(1010,5,900000,300000))
  self.assertEqual((row['open'],row['high'],row['low'],row['close']),(200,204,200,204));self.assertEqual(len(row),10)
  self.assertEqual(x['schema'],'market_data.history.rollup.v1.2');self.assertEqual(x['operation'],'window');self.assertEqual(x['selection'],window(s));self.assertEqual(x['units'],UNITS);self.assertEqual(x['turnover_basis'],BASIS);self.assertFalse(x['execution_authority']);self.assertFalse(x['trading_authorized']);self.assertEqual(x['dataset_fingerprint'],digest({k:v for k,v in x.items() if k!='dataset_fingerprint'}))
  self.assertEqual(x['parents'],[dict(snapshot_id=s['snapshot_id'],dataset_id=e['dataset_id'],dataset_fingerprint=e['dataset_fingerprint'])])
 def test_exact_discriminated_selection_keys_and_closed_operations_refuse_before_read(self):
  for change in ({'operation':'v5'},{'timeframe':'5m'},{'snapshot_ids':[]},{'end_ms':True},{'symbol':False},{'schema':'market_data.history.selection.v1'}):
   r,s,c,e=fixture();s.update(change);conn=Connection(r)
   with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,c)
   self.assertEqual(conn.calls,[])
 def test_catalog_request_trust_revision_and_receipt_preflight_before_read(self):
  changes=[lambda e:e.update(schema='old'),lambda e:e['request'].update(extra=1),lambda e:e['trust'].update(extra=1),lambda e:e['revisions'].append(e['revisions'][0]),lambda e:e['revisions'].pop(),lambda e:e['trust'].update(evidence_class='SYNTHETIC'),lambda e:e['request'].update(schema='market_data.history.request.v1'),lambda e:next(iter(e['trust']['receipts'].values())).update(schema='old')]
  for change in changes:
   r,s,c,e=fixture();entry=next(iter(c.values()));change(entry);s['snapshot_id']=digest(entry);conn=Connection(r)
   with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,{s['snapshot_id']:entry})
   self.assertEqual(conn.calls,[])
 def test_revisions_receipt_and_content_tamper_refuse(self):
  for change in (lambda r:r.reverse(),lambda r:r.pop(),lambda r:r[-1]['candle'].update(turnover=999),lambda r:r[-1].update(available_at_ms=999999),lambda r:r.__setitem__(0,1)):
   r,s,c,e=fixture();change(r)
   with self.assertRaises(ValueError):module().select_snapshot_v12(Connection(r),s,c)
 def test_window_alignment_and_limits_are_closed(self):
  r,s,c,e=fixture()
  for change in ({'timeframe':'1m'},{'start_ms':60000},{'end_ms':240000},{'operation':'minutes'}):
   selection=window(s);selection.update(change)
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,selection,c)
 def test_full_future_rows_financial_and_hash_tamper_refuse(self):
  r,s,c,e=fixture(delay=True)
  for change in (lambda x:x['rows'][-1].update(turnover=-1),lambda x:x['rows'][-1].update(turnover=0),lambda x:x['rows'][-1].update(turnover=True),lambda x:x['rows'][-1].pop('turnover'),lambda x:x.update(turnover_basis='RECONSTRUCTED'),lambda x:x['request']['units'].update(turnover='USD')):
   x=copy.deepcopy(e);change(x);reseal(x)
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(x,window(s),c)
 def test_context_and_exact_math_amount_total_shared_with_volume(self):
  from market_data import numeric_dto
  r,s,c,e=fixture(delay=True)
  with localcontext() as ctx:
   ctx.prec=1
   for signal in ctx.traps:ctx.traps[signal]=True
   before=dict(ctx.flags);x=module().rollup_snapshot_v12(e,window(s),c);self.assertEqual(dict(ctx.flags),before)
  self.assertEqual(x['rows'][0]['turnover'],1010)
  with patch.object(numeric_dto,'amount_total',return_value=12) as total:self.assertEqual(numeric_dto.volume_total([1,2]),12);total.assert_called_once()
 def test_math_refusal_and_overflow_return_no_partial_result(self):
  from market_data import numeric_dto
  r,s,c,e=fixture()
  with patch.object(numeric_dto,'exact_sum',side_effect=ValueError('MATH_REFUSED')):
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,window(s),c)
  with self.assertRaises(ValueError):numeric_dto.amount_total([1e308,1e308])
 def test_hostile_objects_never_receive_callbacks(self):
  class Evil(dict):
   def __iter__(self):raise AssertionError('CALLBACK')
   def __deepcopy__(self,memo):raise AssertionError('CALLBACK')
  r,s,c,e=fixture()
  for value in (Evil(e),dict(e,rows=[Evil(e['rows'][0])])):
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(value,window(s),c)
 def test_snapshot_input_detaches_before_first_math_callback(self):
  import market_math
  r,s,c,e=fixture();expected=copy.deepcopy(e);original=market_math.lossless_nonnegative_binary64_valid;calls=[]
  def mutate(value):
   if not calls:e['rows'][-1]['turnover']=-1;calls.append(True)
   return original(value)
  with patch.object(market_math,'lossless_nonnegative_binary64_valid',side_effect=mutate):result=module().rollup_snapshot_v12(e,window(s),c)
  self.assertTrue(calls);self.assertEqual(result['rows'][0]['turnover'],1010)
 def multipages(self):
  r,a,c,e=fixture(30,asof=3600000);r2,b,c2,e2=fixture(30,start=1800000,asof=3600000);c.update(c2)
  s=dict(schema='market_data.history.selection.v1.2',operation='multipin',snapshot_ids=[a['snapshot_id'],b['snapshot_id']],timeframe='1h',venue='bybit',market_type='linear',symbol='BTCUSDT',start_ms=0,end_ms=3600000)
  return r+r2,s,c
 def test_multipin_ordered_pages_actual_sum_and_parents(self):
  r,s,c=self.multipages();pages=module().plan_multipin_v12(s,c)
  class Pages(Connection):
   def fetchall(self):
    lo,hi=self.calls[-1][1][1:3];return [(r,) for r in self.rows if lo<=r['start_ms']<hi]
  x=module().read_multipin_rollup_v12(Pages(r),s,pages,c)
  self.assertEqual(x['rows'][0]['turnover'],12870);self.assertEqual([p['snapshot_id'] for p in x['parents']],s['snapshot_ids']);self.assertEqual(x['operation'],'multipin')
 def test_multipin_reorder_duplicate_gap_identity_and_lineage_refuse_before_read(self):
  r,s,c=self.multipages()
  for pins in (s['snapshot_ids'][::-1],[s['snapshot_ids'][0]]*2,[s['snapshot_ids'][0]]):
   with self.assertRaises(ValueError):module().plan_multipin_v12(dict(s,snapshot_ids=pins),c)
  for key,value in (('as_of_ms',3600001),('units',{'price':'USD/BTC','volume':'BTC','turnover':'USD'})):
   r,s,c=self.multipages();old=s['snapshot_ids'][1];entry=c.pop(old);entry['request'][key]=value;pin=digest(entry);c[pin]=entry;s['snapshot_ids'][1]=pin
   with self.assertRaises(ValueError):module().plan_multipin_v12(s,c)
 def test_multipin_supplied_pages_cannot_bypass_plan(self):
  r,s,c=self.multipages();pages=module().plan_multipin_v12(s,c);conn=Connection(r)
  with self.assertRaises(ValueError):module().read_multipin_rollup_v12(conn,s,pages[::-1],c)
  self.assertEqual(conn.calls,[])
 def test_series_same_schema_operation_and_bounded_complete_candles(self):
  r,s,c=self.multipages();s['operation']='series';pages=module().plan_multipin_v12(s,c)
  self.assertEqual(len(pages),2)
  for change in ({'snapshot_ids':s['snapshot_ids']*9},{'end_ms':3600000*33},{'timeframe':'5m'},{'end_ms':1209600000+3600000}):
   with self.assertRaises(ValueError):module().plan_multipin_v12(dict(s,**change),c)
 def test_old_export_catalog_and_rollups_keep_golden_bytes(self):
  from test_history_snapshot import snapshot_fixture
  from market_data.history_snapshot import select_snapshot,rollup_snapshot
  r,s,c,e=snapshot_fixture(5,'HISTORICAL');self.assertEqual(select_snapshot(Connection(r),s,c),e)
  self.assertEqual(digest(rollup_snapshot(e,'5m')),'a3f82135a5741a48de2229e4ec47ab3cc2aace1aae52a616639d341960a59a61')
  from market_data.history_snapshot import plan_multipin,read_multipin_rollup
  r,s,c,e=snapshot_fixture(60,'HISTORICAL')
  for schema,expected in (('market_data.history.selection.v3','2b029f164f73eefa0df7b5fcb6fe226c77a1935a28abe52bc2ad4775594dbb6a'),('market_data.history.selection.v4','04cfac848e0025bf882dd13ceed20cbb65e6a1918808aee676f74654d4000a97')):
   q={k:v for k,v in s.items() if k not in ('snapshot_id','schema')};q.update(schema=schema,snapshot_ids=[s['snapshot_id']],timeframe='1h');self.assertEqual(digest(read_multipin_rollup(Connection(r),q,plan_multipin(q,c),c)),expected)

 def test_fully_resealed_invalid_future_amount_is_rejected_by_financial_domain(self):
  from market_data.history_export_v11 import _dataset_content
  r,s,c,e=fixture(delay=True);e['rows'][2]['turnover']=-1
  e['dataset_id']=digest(_dataset_content(e,'market_data.dataset.v1.2'));reseal(e)
  with self.assertRaisesRegex(ValueError,'AMOUNT|FINANCIAL'):module().rollup_snapshot_v12(e,window(s),c)
 def test_fully_resealed_available_clock_not_event_end_and_old_version_refuse(self):
  from market_data.history_export_v11 import _dataset_content
  r,s,c,e=fixture(delay=True)
  for key,value in (('available_at_ms',179999),('watermark_ms',900001),('turnover',None)):
   x=copy.deepcopy(e);x['rows'][2][key]=value;x['dataset_id']=digest(_dataset_content(x,'market_data.dataset.v1.2'));reseal(x)
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(x,window(s),c)
  x=copy.deepcopy(e);x['schema']='market_data.history.v1.1';reseal(x)
  with self.assertRaises(ValueError):module().rollup_snapshot_v12(x,window(s),c)
 def test_delayed_middle_parent_page_max_survives_boundary(self):
  r,s,c=self.multipages();entry=c[s['snapshot_ids'][0]];old=r[15]['dataset_fingerprint'];record=r[15]
  record['available_at_ms']=9000000;record['dataset_fingerprint']=digest({k:v for k,v in record.items() if k!='dataset_fingerprint'});new=record['dataset_fingerprint']
  a=entry['trust']['receipts'].pop(old);entry['trust']['receipt_pins'].pop(old);a.update(fingerprint=new,available_at_ms=9000000);entry['trust']['receipts'][new]=a;entry['trust']['receipt_pins'][new]=digest(a);entry['revisions'][15]=new
  for idx,pin in enumerate(list(s['snapshot_ids'])):
   en=c.pop(pin);en['request']['as_of_ms']=9000000;records=r[:30] if idx==0 else r[30:];env=export_records_v12(records,en['request'],en['trust']);en['dataset_id']=env['dataset_id'];en['dataset_fingerprint']=env['dataset_fingerprint'];newpin=digest(en);c[newpin]=en;s['snapshot_ids'][idx]=newpin
  class Pages(Connection):
   def fetchall(self):
    lo,hi=self.calls[-1][1][1:3];return [(r,) for r in self.rows if lo<=r['start_ms']<hi]
  x=module().read_multipin_rollup_v12(Pages(r),s,module().plan_multipin_v12(s,c),c)
  self.assertEqual(x['rows'][0]['available_at_ms'],9000000);self.assertEqual(x['rows'][0]['watermark_ms'],3600000)
 def test_old_rollup_version_policy_is_closed_and_new_amount_does_not_reconstruct(self):
  from market_data.history_snapshot import _candle
  r,s,c,e=fixture()
  self.assertNotIn('turnover',_candle(e['rows']))
  with self.assertRaises(ValueError):_candle(e['rows'],version='v9')
  x=copy.deepcopy(e);x['rows'][0].pop('turnover')
  with self.assertRaises(ValueError):module().rollup_snapshot_v12(x,window(s),c)
 def test_three_units_and_all_basis_receipt_versions_preflight_cross_page(self):
  for key,value in (('turnover_basis','PROVIDER'),('record_api_version',{'major':1,'minor':1}),('dataset_schema','market_data.dataset.v1.1'),('units',{'price':'USDT/BTC','volume':'BTC'})):
   r,s,c=self.multipages();pin=s['snapshot_ids'][1];entry=c.pop(pin);fp=entry['revisions'][0];entry['trust']['receipts'][fp][key]=value;entry['trust']['receipt_pins'][fp]=digest(entry['trust']['receipts'][fp]);pin=digest(entry);c[pin]=entry;s['snapshot_ids'][1]=pin
   with self.assertRaises(ValueError):module().plan_multipin_v12(s,c)
 def test_series_reads_two_complete_candles_same_rollup_family(self):
  r,s,c=self.multipages();r2,a,c2,e2=fixture(60,start=3600000,asof=7200000)
  for pin in list(s['snapshot_ids']):
   entry=c.pop(pin);entry['request']['as_of_ms']=7200000;rr=r[:30] if entry['request']['start_ms']==0 else r[30:];env=export_records_v12(rr,entry['request'],entry['trust']);entry['dataset_fingerprint']=env['dataset_fingerprint'];new=digest(entry);c[new]=entry;s['snapshot_ids'][s['snapshot_ids'].index(pin)]=new
  c.update(c2);s.update(operation='series',end_ms=7200000);s['snapshot_ids'].append(a['snapshot_id']);r+=r2
  class Pages(Connection):
   def fetchall(self):
    lo,hi=self.calls[-1][1][1:3];return [(r,) for r in self.rows if lo<=r['start_ms']<hi]
  x=module().read_multipin_rollup_v12(Pages(r),s,module().plan_multipin_v12(s,c),c)
  self.assertEqual(x['schema'],'market_data.history.rollup.v1.2');self.assertEqual(x['operation'],'series');self.assertEqual(len(x['rows']),2)

 def test_window_catalog_pin_must_bind_both_independent_parent_hashes(self):
  r,s,c,e=fixture();wrong=dict(window(s),snapshot_id='f'*64)
  with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,wrong,c)
  entry=copy.deepcopy(next(iter(c.values())));entry['dataset_id']='e'*64;pin=digest(entry);changed=dict(window(s),snapshot_id=pin)
  with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,changed,{pin:entry})
  for change in ({'symbol':'ETHUSDT'},{'start_ms':60000},{'end_ms':600000}):
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,dict(window(s),**change),c)
  from market_data.history_export_v11 import _dataset_content
  x=copy.deepcopy(e);x['rows'][-1]['turnover']=999;x['dataset_id']=digest(_dataset_content(x,'market_data.dataset.v1.2'));reseal(x)
  with self.assertRaisesRegex(ValueError,'PARENT_PIN'):module().rollup_snapshot_v12(x,window(s),c)
  x=copy.deepcopy(e);x['request']['units']={'price':'USD/BTC','volume':'BTC','turnover':'USD'};x['dataset_id']=digest(_dataset_content(x,'market_data.dataset.v1.2'));reseal(x)
  with self.assertRaisesRegex(ValueError,'PARENT_PIN'):module().rollup_snapshot_v12(x,window(s),c)
  r,s,c=self.multipages();pin=s['snapshot_ids'][1];entry=c.pop(pin);entry['trust']['receipts'][entry['revisions'][0]]['turnover_basis']='FAKE';new=digest(entry);c[new]=entry;s['snapshot_ids'][1]=new;conn=Connection(r)
  with self.assertRaises(ValueError):module().read_multipin_rollup_v12(conn,s,[],c)
  self.assertEqual(conn.calls,[])

 def test_foreign_selected_and_unused_catalog_keys_refuse_without_callbacks(self):
  calls=[]
  class Foreign(str):
   __hash__=str.__hash__
   def __eq__(self,other):calls.append('EQ');return str.__eq__(self,other)
  for selected in (True,False):
   r,s,c,e=fixture();pin=s['snapshot_id'];foreign={Foreign(pin if selected else 'unused'):c[pin]}
   if not selected:foreign[pin]=c[pin]
   calls.clear();before=[(id(k),id(v)) for k,v in foreign.items()];conn=Connection(r)
   with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,foreign)
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,window(s),foreign)
   self.assertEqual(calls,[]);self.assertEqual(conn.calls,[]);self.assertEqual([(id(k),id(v)) for k,v in foreign.items()],before)
   r,ms,mc=self.multipages();foreign={Foreign(k):v for k,v in mc.items()} if selected else dict(mc)
   if not selected:foreign[Foreign('unused')]=next(iter(mc.values()))
   calls.clear();conn=Connection(r)
   with self.assertRaises(ValueError):module().plan_multipin_v12(ms,foreign)
   with self.assertRaises(ValueError):module().read_multipin_rollup_v12(conn,ms,[],foreign)
   self.assertEqual(calls,[]);self.assertEqual(conn.calls,[])
 def test_foreign_nested_field_keys_refuse_before_callbacks_math_or_reads(self):
  calls=[]
  class Foreign(str):
   __hash__=str.__hash__
   def __eq__(self,other):calls.append('EQ');return str.__eq__(self,other)
  for which in ('selection','entry','request','trust','units','receipt','receipt_pins','payload','row','source'):
   r,s,c,e=fixture();entry=c[s['snapshot_id']];receipt=entry['trust']['receipts'][entry['revisions'][0]]
   maps={'selection':s,'entry':entry,'request':entry['request'],'trust':entry['trust'],'units':entry['request']['units'],'receipt':receipt,'receipt_pins':entry['trust']['receipt_pins'],'payload':e,'row':e['rows'][0],'source':e['source']}
   target=maps[which];key=next(iter(target));value=target.pop(key);target[Foreign(key)]=value;calls.clear();before=[(id(k),id(v)) for k,v in target.items()];conn=Connection(r)
   with patch('market_data.numeric_dto.exact_sum',side_effect=AssertionError('MATH_BEFORE_LITERAL_ADMISSION')):
    with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,window(s),c)
   if which not in ('payload','row','source'):
    with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,c)
   self.assertEqual(calls,[]);self.assertEqual(conn.calls,[]);self.assertEqual([(id(k),id(v)) for k,v in target.items()],before)
 def test_unused_nested_catalog_foreign_leaves_cannot_be_ignored(self):
  calls=[]
  class Foreign(str):
   __hash__=str.__hash__
   def __eq__(self,other):calls.append('EQ');return str.__eq__(self,other)
  class Leaf:
   def __deepcopy__(self,memo):calls.append('COPY');return self
   def __str__(self):calls.append('STR');return 'ignored'
  for unused in ({Foreign('request'):{'units':UNITS}},{'request':{'units':{Foreign('turnover'):'USDT'}}},{'request':{'extra':Leaf()}}):
   r,s,c,e=fixture();c['unused']=unused;calls.clear();conn=Connection(r)
   with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,c)
   with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,window(s),c)
   self.assertEqual(calls,[]);self.assertEqual(conn.calls,[])
 def test_catalog_full_literal_graph_is_bounded_before_selected_lookup(self):
  r,s,c,e=fixture();c['unused']='x'*(8*1024*1024+1);conn=Connection(r)
  with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,c)
  with self.assertRaises(ValueError):module().rollup_snapshot_v12(e,window(s),c)
  self.assertEqual(conn.calls,[])

 def test_continuation_requires_exact_bool_before_any_admission_or_cursor_callback(self):
  calls=[]
  class Foreign:
   def __bool__(self):calls.append('BOOL');return True
  class Fake(Connection):
   def cursor(self):calls.append('CURSOR');return self
  for flag in (Foreign(),0,1,2,'','true',None,[],{}):
   r,s,c,e=fixture();conn=Fake(r);calls.clear()
   with patch.object(module(),'_selection',side_effect=AssertionError('ADMISSION_BEFORE_FLAG_CHECK')):
    with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,c,continuing=flag)
   with self.assertRaises(ValueError):module().select_snapshot_v12(conn,s,c,continuing=flag)
   self.assertEqual(calls,[]);self.assertEqual(conn.calls,[])
 def test_literal_false_starts_readonly_and_true_preserves_continuation_semantics(self):
  r,s,c,e=fixture()
  for flag in (False,True):
   conn=Connection(r);self.assertEqual(module().select_snapshot_v12(conn,s,c,continuing=flag),e)
   setup=[sql for sql,params in conn.calls if sql.startswith('SET ')]
   self.assertEqual(bool(setup),not flag)
   if not flag:self.assertIn('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY',setup)
