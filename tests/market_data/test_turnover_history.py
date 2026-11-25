"""Synthetic turnover lineage and versioned history only; no connection/provider."""
import copy,json,unittest
from decimal import Decimal,localcontext
from unittest.mock import patch
from market_data.footprint_state import FootprintBuilder
from market_data.public_trades import Trade
from market_data.provenance import minute_record,minute_record_v12,digest
from market_data.history_export_v12 import export_records_v12
UNITS={'price':'USDT/BTC','volume':'BTC','turnover':'USDT'}
BASIS='EXECUTED_TRADE_PRICE_TIMES_QUANTITY_SUM'
AVAILABILITY='CALLER_DECLARED_NOT_COMMIT_OR_PIT'
def source():return dict(identity='fixture',source_revision='a'*40,epoch='00000000-0000-0000-0000-000000000001',market_type='linear',representation='live_trade_aggregate')
def raw_rows(n=2):
 b=FootprintBuilder('.01')
 for i in range(n):
  b.add(Trade('BTCUSDT',i*60000+1000,'100.01','2','Buy','a'+str(i)))
  b.add(Trade('BTCUSDT',i*60000+2000,'100.09','3','Sell','b'+str(i)))
 rows=b.pop_closed(n*60000)
 for row in rows:row['source_provenance']=source()
 return rows
def fixture(n=2):
 records=[minute_record_v12(row,(i+1)*60000+1000,'fixture',available_at_ms=(i+1)*60000,units=UNITS) for i,row in enumerate(raw_rows(n))]
 receipts={}
 for i,r in enumerate(records):
  fp=r['dataset_fingerprint'];receipts[fp]=dict(schema='market_data.history.receipt.v1.2',record_api_version={'major':1,'minor':2},dataset_schema='market_data.dataset.v1.2',fingerprint=fp,venue='bybit',available_at_ms=r['available_at_ms'],watermark_ms=(i+1)*60000,complete=True,units=dict(UNITS),evidence_class='SYNTHETIC',turnover_basis=BASIS)
 q=dict(schema='market_data.history.request.v1.2',venue='bybit',market_type='linear',symbol='BTCUSDT',start_ms=0,end_ms=n*60000,as_of_ms=n*60000+1000,max_age_ms=60000,units=dict(UNITS))
 trust=dict(schema='market_data.history.trust.v1.2',identity='fixture',source_revision='a'*40,epoch=source()['epoch'],receipts=receipts,receipt_pins={fp:digest(r) for fp,r in receipts.items()},evidence_class='SYNTHETIC')
 return records,q,trust
class TurnoverHistoryTests(unittest.TestCase):
 def test_actual_unrounded_trade_notional_and_dedup_are_preserved(self):
  b=FootprintBuilder('.1');a=Trade('BTCUSDT',1000,'.25','100.00001','Buy','a');c=Trade('BTCUSDT',2000,'.45','100.00001','Sell','b');self.assertTrue(b.add(a));self.assertTrue(b.add(c));self.assertFalse(b.add(a));row,=b.pop_closed(60000)
  self.assertEqual(row['turnover'],70.000007);self.assertEqual(row['turnover_basis'],BASIS);self.assertEqual(row['trade_count'],2);self.assertFalse(b.add(a))
 def test_math_notional_and_sum_refusal_precedes_any_bucket_mutation(self):
  for target in ('wall_notional','exact_sum'):
   b=FootprintBuilder('.01');b.add(Trade('BTCUSDT',1000,'100','1','Buy','old'));before=copy.deepcopy((b.buckets,b.finalized_through_ms))
   with patch('market_data.footprint_state.'+target,side_effect=ValueError('MATH_REFUSED')):
    with self.assertRaisesRegex(ValueError,'MATH_REFUSED'):b.add(Trade('BTCUSDT',2000,'101','2','Sell','new'))
   self.assertEqual((b.buckets,b.finalized_through_ms),before)
 def test_new_bucket_not_published_on_notional_refusal(self):
  b=FootprintBuilder('.01')
  with patch('market_data.footprint_state.wall_notional',side_effect=ValueError('NO_AMOUNT')):
   with self.assertRaises(ValueError):b.add(Trade('BTCUSDT',1000,'100','1','Buy','a'))
  self.assertEqual(b.buckets,{})
 def test_turnover_dto_overflow_or_nonzero_underflow_never_finalizes_any_bucket(self):
  for price,quantity in (('1e200','1e200'),('1e-200','1e-200')):
   b=FootprintBuilder('.01');b.add(Trade('BTCUSDT',1000,'1','1','Buy','good'));b.add(Trade('BTCUSDT',61000,price,quantity,'Buy','bad'))
   with self.assertRaises(ValueError):b.pop_closed(120000)
   self.assertEqual(set(b.buckets),{('BTCUSDT',0),('BTCUSDT',60000)});self.assertEqual(b.finalized_through_ms,{})
 def test_new_record_has_explicit_quote_units_availability_and_basis(self):
  records,q,t=fixture(1);r=records[0];self.assertEqual(r['api_version'],{'major':1,'minor':2});self.assertEqual(r['candle']['turnover'],500.29);self.assertEqual(r['units'],UNITS);self.assertEqual(r['available_at_ms'],60000);self.assertEqual(r['turnover_basis'],BASIS);self.assertEqual(r['availability_basis'],AVAILABILITY);self.assertFalse(r['execution_authority']);self.assertFalse(r['trading_authorized']);self.assertEqual(r['source_authentication'],'NOT_EVALUATED');self.assertEqual(r['dataset_fingerprint'],digest({k:v for k,v in r.items() if k!='dataset_fingerprint'}))
 def test_legacy_minute_record_bytes_unchanged_and_new_record_detaches_input(self):
  row=raw_rows(1)[0];old=copy.deepcopy(row);old.pop('turnover');old.pop('turnover_basis');self.assertEqual(minute_record(row,61000,'fixture'),minute_record(old,61000,'fixture'))
  legacy=minute_record(old,61000,'fixture');before=copy.deepcopy(legacy);new=minute_record_v12(row,61000,'fixture',available_at_ms=60000,units=UNITS);self.assertEqual(legacy,before);self.assertNotEqual(new['dataset_fingerprint'],legacy['dataset_fingerprint']);row['turnover']=1;self.assertEqual(new['candle']['turnover'],500.29)
 def test_missing_turnover_or_basis_never_defaulted_or_reconstructed(self):
  for key in ('turnover','turnover_basis'):
   row=raw_rows(1)[0];row.pop(key)
   with self.assertRaises(ValueError):minute_record_v12(row,61000,'fixture',available_at_ms=60000,units=UNITS)
 def test_new_record_literal_units_and_clock_domain(self):
  for units in ({'price':'USDT/BTC','volume':'BTC'},{**UNITS,'turnover':'USD'},{**UNITS,'turnover':True}):
   with self.assertRaises(ValueError):minute_record_v12(raw_rows(1)[0],61000,'fixture',available_at_ms=60000,units=units)
  for known in (True,None,59999,1.0,2**53):
   with self.assertRaises(ValueError):minute_record_v12(raw_rows(1)[0],61000,'fixture',available_at_ms=known,units=UNITS)
 def test_new_record_refuses_bad_turnover_and_false_basis(self):
  for value in (None,True,float('nan'),float('inf'),-1,2**53+1):
   row=raw_rows(1)[0];row['turnover']=value
   with self.assertRaises(ValueError):minute_record_v12(row,61000,'fixture',available_at_ms=60000,units=UNITS)
  row=raw_rows(1)[0];row['turnover_basis']='VWAP_TIMES_VOLUME'
  with self.assertRaises(ValueError):minute_record_v12(row,61000,'fixture',available_at_ms=60000,units=UNITS)
 def test_export_new_version_carries_actual_turnover_and_receipt_pins(self):
  r,q,t=fixture();x=export_records_v12(r,q,t);self.assertEqual(x['schema'],'market_data.history.v1.2');self.assertEqual(x['request']['units'],UNITS);self.assertEqual([v['turnover'] for v in x['rows']],[500.29,500.29]);self.assertEqual(len(x['rows'][0]),14);self.assertEqual(x['rows'][0]['source_receipt_hash'],t['receipt_pins'][r[0]['dataset_fingerprint']]);self.assertEqual(x['turnover_basis'],BASIS);self.assertEqual(x['availability_basis'],AVAILABILITY);self.assertFalse(x['execution_authority']);self.assertFalse(x['trading_authorized']);self.assertEqual(x['source_authentication'],'NOT_EVALUATED');self.assertEqual(x['dataset_fingerprint'],digest({k:v for k,v in x.items() if k!='dataset_fingerprint'}))
 def test_content_identity_is_stable_across_admission_asof_but_full_fingerprint_changes(self):
  r,q,t=fixture();a=export_records_v12(r,q,t);b=export_records_v12(r,{**q,'as_of_ms':q['as_of_ms']+1000},t);self.assertEqual(a['dataset_id'],b['dataset_id']);self.assertNotEqual(a['dataset_fingerprint'],b['dataset_fingerprint'])
 def test_legacy_missing_turnover_cannot_be_promoted(self):
  from test_history_export import fixture as old_fixture
  r,q,t=old_fixture(2);q['schema']='market_data.history.request.v1.2';q['units']=dict(UNITS)
  with self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_old_request_or_trust_version_refuses(self):
  for container,key,value in (('q','schema','market_data.history.request.v1'),('t','schema','market_data.history.trust.v1')):
   r,q,t=fixture();(q if container=='q' else t)[key]=value
   with self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_receipt_record_dataset_and_basis_versions_must_agree_even_when_resealed(self):
  for key,value in (('schema','market_data.history.receipt.v1'),('record_api_version',{'major':1,'minor':1}),('dataset_schema','market_data.dataset.v1.1'),('turnover_basis','PROVIDER_KLINE')):
   r,q,t=fixture();fp=r[0]['dataset_fingerprint'];t['receipts'][fp][key]=value;t['receipt_pins'][fp]=digest(t['receipts'][fp])
   with self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_receipt_availability_cannot_replace_declared_record_availability(self):
  r,q,t=fixture();fp=r[0]['dataset_fingerprint'];t['receipts'][fp]['available_at_ms']+=1;t['receipt_pins'][fp]=digest(t['receipts'][fp])
  with self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_turnover_units_receipts_or_record_tampering_fail(self):
  for mutate in (lambda r,q,t:r[0]['candle'].update(turnover=999),lambda r,q,t:q['units'].update(turnover='USD'),lambda r,q,t:t.update(receipt_pins={})):
   r,q,t=fixture();mutate(r,q,t)
   with self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_watermark_after_availability_or_false_completeness_refuses(self):
  for key,value in (('watermark_ms',60001),('complete',False)):
   r,q,t=fixture();fp=r[0]['dataset_fingerprint'];t['receipts'][fp][key]=value;t['receipt_pins'][fp]=digest(t['receipts'][fp])
   with self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_legacy_export_golden_byte_hashes_are_unchanged(self):
  from test_history_export import fixture as old_fixture
  from market_data.history_export import export_records
  from market_data.history_export_v11 import export_records_v11
  r,q,t=old_fixture(2);self.assertEqual(digest(export_records(r,q,t)),'28e6c51bb944bd925b997aad0bd1d4249277ab03baa0015ce4aa9d6a094c2f68');self.assertEqual(digest(export_records_v11(r,q,t)),'719fa403c754f0cb2d658d79b69269ccc30392ae09fa3a145bec61921fd77a07')
 def test_snapshots_detach_before_first_math_owner_call(self):
  import market_math
  row=raw_rows(1)[0];units=dict(UNITS);original=market_math.historical_aggregate_integrity
  def mutate_then_check(value):row['turnover']=999;units['turnover']='USD';return original(value)
  with patch('market_data.provenance.historical_aggregate_integrity',side_effect=mutate_then_check):r=minute_record_v12(row,61000,'fixture',available_at_ms=60000,units=units)
  self.assertEqual((r['candle']['turnover'],r['units']['turnover']),(500.29,'USDT'))
 def test_hostile_literal_graphs_refuse_without_copy_callbacks(self):
  class Bad(dict):
   def __deepcopy__(self,memo):raise AssertionError('FOREIGN_COPY')
  with self.assertRaises(ValueError):minute_record_v12(Bad(),61000,'fixture',available_at_ms=60000,units=UNITS)
  r,q,t=fixture()
  with self.assertRaises(ValueError):export_records_v12(Bad(),q,t)
 def test_decimal_context_flags_and_traps_are_unchanged(self):
  with localcontext() as c:
   c.prec=1
   for flag in c.flags:c.flags[flag]=True;c.traps[flag]=True
   before=(dict(c.flags),dict(c.traps));r,q,t=fixture();x=export_records_v12(r,q,t);self.assertEqual(x['rows'][0]['turnover'],500.29);self.assertEqual((dict(c.flags),dict(c.traps)),before)

 def test_new_rows_supply_real_turnover_to_existing_math_volatility_abi(self):
  from market_compute_api import causal_volatility_metrics
  r,q,t=fixture();x=export_records_v12(r,q,t);rows=tuple({k:row[k] for k in ('event_start_ms','open','high','low','close','volume','turnover','available_at_ms')} for row in x['rows']);result=causal_volatility_metrics(rows,window=2,percentile_lookback=2,bar_duration_ms=60000)
  self.assertEqual(len(result),1);self.assertEqual(result[0][1],120000);self.assertEqual(result[0][7],1.0)
  missing=[dict(row) for row in rows];missing[0].pop('turnover')
  with self.assertRaises(ValueError):causal_volatility_metrics(missing,window=2,percentile_lookback=2,bar_duration_ms=60000)
 def test_export_detaches_all_records_request_and_trust_before_numeric_owner(self):
  import market_math
  r,q,t=fixture();original=market_math.lossless_nonnegative_binary64_valid
  def mutate_then_validate(value):r[0]['candle']['turnover']=999;q['units']['turnover']='USD';t['receipt_pins'].clear();return original(value)
  with patch('market_math.lossless_nonnegative_binary64_valid',side_effect=mutate_then_validate):x=export_records_v12(r,q,t)
  self.assertEqual(x['rows'][0]['turnover'],500.29);self.assertEqual(x['request']['units']['turnover'],'USDT')
 def test_extra_receipts_or_boolean_version_are_not_promoted(self):
  r,q,t=fixture();t['receipts']['b'*64]=dict(next(iter(t['receipts'].values())));t['receipt_pins']['b'*64]=digest(t['receipts']['b'*64])
  with self.assertRaises(ValueError):export_records_v12(r,q,t)
  r,q,t=fixture();fp=r[0]['dataset_fingerprint'];t['receipts'][fp]['record_api_version']['major']=True;t['receipt_pins'][fp]=digest(t['receipts'][fp])
  with self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_actual_event_time_ohlc_legacy_lifecycle_remains_unchanged(self):
  b=FootprintBuilder(1);b.add(Trade('BTCUSDT',2000,'2','1','Buy','b'));b.add(Trade('BTCUSDT',1000,'1','1','Buy','a'));self.assertFalse(b.add(Trade('BTCUSDT',1000,'1','1','Buy','a')));row,=b.pop_closed(60000)
  self.assertEqual((row['open'],row['close'],row['trade_count'],row['turnover']),(1,2,2,3));self.assertFalse(b.add(Trade('BTCUSDT',3000,'3','1','Buy','c')))

 def test_resealed_boolean_record_clocks_are_not_integer_identities(self):
  for clock in ('start_ms','end_ms','available_at_ms','source_event_start_ms','source_event_end_ms','ingestion_ms'):
   r,q,t=fixture();old=r[0]['dataset_fingerprint'];receipt=t['receipts'].pop(old);t['receipt_pins'].pop(old);r[0][clock]=False;fp=digest({k:v for k,v in r[0].items() if k!='dataset_fingerprint'});r[0]['dataset_fingerprint']=fp;receipt['fingerprint']=fp;t['receipts'][fp]=receipt;t['receipt_pins'][fp]=digest(receipt)
   with self.subTest(clock=clock),self.assertRaises(ValueError):export_records_v12(r,q,t)
 def test_foreign_metaclass_comparison_is_never_called_on_literal_refusal(self):
  from market_data.history_contract import _snapshot_json,_number
  class Meta(type):
   def __eq__(self,other):raise AssertionError('FOREIGN_METACLASS_EQUALITY')
   def __ne__(self,other):raise AssertionError('FOREIGN_METACLASS_INEQUALITY')
  class Foreign(metaclass=Meta):pass
  foreign=Foreign()
  for raw in (foreign,[foreign],{'future':[foreign]}):
   with self.assertRaises(ValueError):_snapshot_json(raw)
  with self.assertRaises(ValueError):_number(foreign)
  row=raw_rows(1)[0];row['quality_reasons']=[foreign]
  with self.assertRaises(ValueError):minute_record_v12(row,61000,'fixture',available_at_ms=60000,units=UNITS)
  r,q,t=fixture();r[1]['unavailable_future_metadata']=foreign
  with self.assertRaises(ValueError):export_records_v12(r,q,t)

 def test_executed_turnover_zero_relation_uses_actual_math_owner(self):
  from market_data.history_contract import _candle
  row=raw_rows(1)[0]
  for turnover,buy,sell in ((0.0,2.0,3.0),(1.0,0.0,0.0)):
   candle={k:row[k] for k in ('open','high','low','close','buy_volume','sell_volume','turnover')};candle.update(turnover=turnover,buy_volume=buy,sell_volume=sell)
   with self.assertRaises(ValueError):_candle(candle)
  candle.update(turnover=0.0,buy_volume=0.0,sell_volume=0.0);_candle(candle)
 def test_executed_turnover_owner_receives_literal_actual_amounts_and_exact_bool(self):
  from market_data.history_contract import _candle
  row=raw_rows(1)[0];candle={k:row[k] for k in ('open','high','low','close','buy_volume','sell_volume','turnover')}
  with patch('market_math.executed_notional_consistent',return_value=True) as owner:
   _candle(candle);owner.assert_called_once_with(500.29,5.0)
  for refused in (False,1,None):
   with patch('market_math.executed_notional_consistent',return_value=refused),self.assertRaises(ValueError):_candle(candle)

 def test_zero_turnover_positive_volume_refuses_factory_and_resealed_export(self):
  row=raw_rows(1)[0];row['turnover']=0.0
  with self.assertRaises(ValueError):minute_record_v12(row,61000,'fixture',available_at_ms=60000,units=UNITS)
  r,q,t=fixture();old=r[0]['dataset_fingerprint'];receipt=t['receipts'].pop(old);t['receipt_pins'].pop(old);r[0]['candle']['turnover']=0.0;fp=digest({k:v for k,v in r[0].items() if k!='dataset_fingerprint'});r[0]['dataset_fingerprint']=fp;receipt['fingerprint']=fp;t['receipts'][fp]=receipt;t['receipt_pins'][fp]=digest(receipt)
  with self.assertRaises(ValueError):export_records_v12(r,q,t)

 def test_builder_captures_complete_trade_before_each_numeric_owner(self):
  import market_data.footprint_state as owner
  for name in ('price_bucket','footprint_cell_update','wall_notional','exact_sum'):
   b=FootprintBuilder('.01');trade=Trade('BTCUSDT',1000,'100','2','Buy','original');original=getattr(owner,name)
   def mutate(*args,**kwargs):
    for key,value in dict(symbol='ETHUSDT',ts_ms=61000,ts_us=61000000,price=Decimal('999'),qty=Decimal('999'),side='Sell',trade_id='changed').items():object.__setattr__(trade,key,value)
    return original(*args,**kwargs)
   with patch('market_data.footprint_state.'+name,side_effect=mutate):self.assertTrue(b.add(trade))
   self.assertFalse(b.add(Trade('BTCUSDT',1000,'100','2','Buy','original')))
   row,=b.pop_closed(60000);self.assertEqual((row['symbol'],row['start_ms'],row['source_event_start_ms'],row['source_event_end_ms'],row['open'],row['buy_volume'],row['sell_volume'],row['turnover']),('BTCUSDT',0,1000,1000,100.,2.,0.,200.))
 def test_builder_literal_preflight_refuses_before_any_math_or_mutation(self):
  class Foreign:
   def __str__(self):raise AssertionError('FOREIGN_STRING')
   def __float__(self):raise AssertionError('FOREIGN_FLOAT')
  for key,value in (('symbol',Foreign()),('ts_ms',False),('ts_us',False),('ts_us',2000000),('trade_id',Foreign()),('side',Foreign()),('side','buy'),('price',Foreign()),('qty',Foreign()),('price','100'),('qty',1)):
   b=FootprintBuilder('.01');trade=Trade('BTCUSDT',1000,'100','2','Buy','original');object.__setattr__(trade,key,value)
   with patch('market_data.footprint_state.price_bucket',side_effect=AssertionError('MATH_BEFORE_PREFLIGHT')),self.assertRaises(ValueError):b.add(trade)
   self.assertEqual((b.buckets,b.finalized_through_ms),({},{}))
  with self.assertRaises(ValueError):b.add(Foreign())
 def test_builder_snapshot_owner_refusal_is_atomic_for_new_and_existing_bucket(self):
  for existing in (False,True):
   b=FootprintBuilder('.01')
   if existing:b.add(Trade('BTCUSDT',500,'99','1','Sell','first'))
   before=copy.deepcopy((b.buckets,b.finalized_through_ms));trade=Trade('BTCUSDT',1000,'100','2','Buy','original')
   def refuse(*args):object.__setattr__(trade,'trade_id','changed');object.__setattr__(trade,'ts_ms',61000);raise ValueError('OWNER_REFUSAL')
   with patch('market_data.footprint_state.wall_notional',side_effect=refuse),self.assertRaises(ValueError):b.add(trade)
   self.assertEqual((b.buckets,b.finalized_through_ms),before)
