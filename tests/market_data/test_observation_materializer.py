"""Pure raw-window orchestration; exact source declarations, never durable ACK."""
import hashlib,importlib.util,json,unittest
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch
from market_data.raw_capture import encode_observation,decode_observation
from market_data.timestamp_codec import utc_from_epoch_milliseconds

class ObservationMaterializerTests(unittest.TestCase):
 def api(self):
  self.assertIsNotNone(importlib.util.find_spec('market_data.observation_materializer'),'bounded observation materializer missing')
  from market_data import observation_materializer as api
  return api
 def cfg(self,**changes):
  a=self.api();out=dict(instrument={'exchange':'bybit','category':'linear','symbol':'BTCUSDT','instrument_version':'1'},producer_source_revision='1'*40,source_kind='PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED',endpoint='wss://stream.bybit.com/v5/public/linear',anchor=a.ObservationChainAnchor('11111111-1111-4111-8111-111111111111',1,None),producer_identity='declared-fixture',source_epoch='22222222-2222-4222-8222-222222222222',tick_size=D(1),units={'price':'USDT/BTC','volume':'BTC','turnover':'USDT'},as_of_ms=180000,closed_through_ms=60000,finalization_available_at_ms=130000,ingestion_ms=140000)
  out.update(changes);return out
 def trade(self,identity='a',*,time=30000,price='100',qty='2',side='Buy'):
  return {'s':'BTCUSDT','T':time,'p':price,'v':qty,'S':side,'i':identity}
 def window(self,batches=None,*,ack=True,validate=True,tail=()):
  a=self.api();cfg=self.cfg();rows=[];head=None;ordinal=0
  def emit(kind,receive,payload=None,frame=None,reason=None):
   nonlocal ordinal,head
   ordinal+=1;stamp=utc_from_epoch_milliseconds(receive).isoformat(timespec='milliseconds').replace('+00:00','Z')
   raw=encode_observation(dict(schema='market_data.raw-capture-observation.v2',instrument=cfg['instrument'],producer_source_revision=cfg['producer_source_revision'],source_kind=cfg['source_kind'],endpoint=cfg['endpoint'],connection_id=cfg['anchor'].connection_id,observation_index=str(ordinal),kind=kind,received_at_utc=stamp,received_monotonic_ns=str(ordinal*1000) if kind=='frame' or frame is None else decode_observation(rows[-1].observation_bytes)['received_monotonic_ns'],payload_kind='BINARY_APPLICATION_PAYLOAD' if payload is not None else 'NONE',payload_sha256=None if payload is None else hashlib.sha256(payload).hexdigest(),payload_bytes=str(0 if payload is None else len(payload)),frame_metadata_sha256=frame,previous_metadata_sha256=head,exchange_event_at_utc=None,sequence=None,update_id=None,reason=reason,publication='LOCAL_UNATTESTED',archive=None))
   rows.append(a.RawObservation(raw,payload));head=hashlib.sha256(raw).hexdigest();return head
  if ack:emit('frame',1000,b'{"op":"subscribe","success":true}')
  batches=[(120000,[self.trade(),self.trade('b',time=45000,price='101',qty='1',side='Sell')])] if batches is None else batches
  for receive,trades in batches:
   payload=json.dumps({'topic':'publicTrade.BTCUSDT','data':trades},separators=(',',':')).encode();frame=emit('frame',receive,payload)
   if validate:emit('validated',receive,frame=frame)
  for kind,receive,reason in tail:emit(kind,receive,reason=reason)
  return tuple(rows)
 def rewrite(self,window,changes):
  a=self.api();head=None;hashes={};out=[]
  for index,pair in enumerate(window):
   meta=decode_observation(pair.observation_bytes);old=hashlib.sha256(pair.observation_bytes).hexdigest();meta.update(changes.get(index,{}));meta['previous_metadata_sha256']=head
   if meta['frame_metadata_sha256'] in hashes:meta['frame_metadata_sha256']=hashes[meta['frame_metadata_sha256']]
   raw=encode_observation(meta);head=hashlib.sha256(raw).hexdigest();hashes[old]=head;out.append(a.RawObservation(raw,pair.payload_bytes))
  return tuple(out)
 def run_api(self,window=None,**changes):return self.api().materialize_observations_v12(self.window() if window is None else window,**self.cfg(**changes))
 def record(self,result,index=0):return json.loads(result.minutes[index].record_bytes)
 def no_accum(self,call):
  with patch('market_data.footprint_state.FootprintBuilder.add',side_effect=AssertionError('ACCUMULATION_CALLED')):
   with self.assertRaises(ValueError):call()
 def test_actual_turnover_ohlc_and_poc_reuse_canonical_builder(self):
  result=self.run_api();row=self.record(result);self.assertEqual(row['api_version'],{'major':1,'minor':2});self.assertEqual(row['candle']['turnover'],301.0)
  self.assertEqual(tuple(row['candle'][k] for k in ('open','high','low','close','buy_volume','sell_volume','delta','trade_count','poc_price')),(100.,101.,100.,101.,2.,1.,1.,2,100.))
  self.assertEqual(row['status'],'PARTIAL');self.assertEqual(row['source_authentication'],'NOT_EVALUATED');self.assertIs(row['source_identity_verified'],False)
 def test_available_clock_is_conservative_max_of_three_explicit_declarations(self):
  row=self.record(self.run_api());self.assertEqual(row['available_at_ms'],140000);self.assertEqual(row['ingestion_ms'],140000)
  row=self.record(self.run_api(finalization_available_at_ms=170000));self.assertEqual(row['available_at_ms'],170000)
 def test_full_original_window_and_advisory_cursor_never_claim_commit_or_resume(self):
  window=self.window();result=self.run_api(window);self.assertEqual(result.window,window);self.assertIsNot(result.window[0],window[0]);self.assertEqual(result.advisory_cursor.next_observation_index,4)
  self.assertIs(result.advisory_cursor.durable_acknowledgement,False);self.assertIs(result.pending_subset_independently_resumable,False);self.assertEqual(result.publication,'LOCAL_UNATTESTED')
 def test_open_future_event_and_future_receive_remain_pending_original_subset(self):
  window=self.window([(120000,[self.trade()]),(150000,[self.trade('open',time=90000)]),(160000,[self.trade('future',time=200000)]),(240000,[self.trade('future-receive',time=50000)])]);result=self.run_api(window)
  self.assertEqual(len(result.minutes),1);self.assertEqual(result.pending_observation_indices,(4,5,6,7,8,9));self.assertEqual(result.pending,window[3:]);self.assertEqual({x.reason for x in result.pending_executions},{'MINUTE_OPEN','FUTURE_EVENT','FUTURE_OBSERVATION'})
 def test_pending_subset_is_not_a_chain_resume_or_previous_window_replacement(self):
  result=self.run_api(self.window([(120000,[self.trade()]),(150000,[self.trade('open',time=90000)])]));self.no_accum(lambda:self.run_api(result.pending))
  with self.assertRaises(TypeError):self.api().materialize_observations_v12(self.window(),prior_pending=result.pending,**self.cfg())
 def test_exact_duplicates_are_idempotent_and_conflicting_future_duplicate_refuses(self):
  a=self.run_api(self.window([(120000,[self.trade()])]))
  b=self.run_api(self.window([(120000,[self.trade()]),(150000,[self.trade()])]))
  self.assertEqual(self.record(a)['candle'],self.record(b)['candle']);self.assertEqual(self.record(b)['candle']['trade_count'],1)
  self.no_accum(lambda:self.run_api(self.window([(120000,[self.trade()]),(240000,[self.trade(price='999')])])))
 def test_payload_size_and_actual_payload_hash_bind_before_accumulation(self):
  window=self.window();a=self.api();bad=window[:1]+(a.RawObservation(window[1].observation_bytes,b'changed'),)+window[2:];self.no_accum(lambda:self.run_api(bad))
  self.no_accum(lambda:self.run_api(self.rewrite(window,{1:{'payload_sha256':'0'*64}})))
 def test_raw_metadata_byte_identity_and_predecessor_chain_are_exact(self):
  window=self.window();a=self.api();self.no_accum(lambda:self.run_api((a.RawObservation(window[0].observation_bytes+b' ',window[0].payload_bytes),)+window[1:]))
  bad=decode_observation(window[1].observation_bytes);bad['previous_metadata_sha256']='0'*64;raw=encode_observation(bad);self.no_accum(lambda:self.run_api(window[:1]+(a.RawObservation(raw,window[1].payload_bytes),)+window[2:]))
 def test_expected_source_instrument_revision_endpoint_and_connection_are_closed(self):
  for changes in ({'producer_source_revision':'2'*40},{'source_kind':'SYNTHETIC','endpoint':'synthetic://bybit/linear'},{'connection_id':'33333333-3333-4333-8333-333333333333'},{'instrument':{'exchange':'bybit','category':'linear','symbol':'ETHUSDT','instrument_version':'1'}}):
   self.no_accum(lambda changes=changes:self.run_api(self.rewrite(self.window(),{1:changes})))
 def test_validated_marker_binds_actual_frame_digest_and_receive_clocks(self):
  for changes in ({'frame_metadata_sha256':'0'*64},{'received_at_utc':'1970-01-01T00:02:01.000Z'},{'received_monotonic_ns':'999'}):self.no_accum(lambda changes=changes:self.run_api(self.rewrite(self.window(),{2:changes})))
 def test_orphan_duplicate_and_unsupported_validation_markers_refuse(self):
  window=self.window();self.no_accum(lambda:self.run_api(self.rewrite(window,{2:{'frame_metadata_sha256':'a'*64}})))
  self.no_accum(lambda:self.run_api(self.rewrite(window,{2:{'sequence':'1'}})))
 def test_control_and_unvalidated_raw_frames_are_preserved_without_empty_minutes(self):
  a=self.run_api(self.window(batches=[]));self.assertEqual(a.minutes,());self.assertEqual(len(a.window),1)
  b=self.run_api(self.window(validate=False));self.assertEqual(b.minutes,());self.assertEqual(b.pending_observation_indices,(2,));self.assertEqual(b.pending,self.window(validate=False)[1:])
 def test_known_gap_degrades_candidates_without_completeness_or_source_grant(self):
  result=self.run_api(self.window(tail=(('gap_observation',160000,'buffer_pressure'),)),ingestion_ms=170000);row=self.record(result)
  self.assertEqual(row['quality_status'],'DEGRADED');self.assertEqual(row['status'],'PARTIAL');self.assertIs(row['coverage']['exchange_completeness_attested'],False);self.assertIs(result.trading_authorized,False)
 def test_late_finalized_input_refuses_before_builder_accumulation(self):self.no_accum(lambda:self.run_api(already_finalized_through_ms=0))
 def test_all_window_clocks_and_units_preflight_before_accumulation(self):
  for changes in ({'as_of_ms':True},{'closed_through_ms':60001},{'finalization_available_at_ms':59999},{'finalization_available_at_ms':180001},{'ingestion_ms':119999},{'units':{'price':'USDT','volume':'BTC','turnover':'USDT'}}):self.no_accum(lambda changes=changes:self.run_api(**changes))
 def test_future_inputs_do_not_fail_because_ingestion_precedes_receive(self):
  result=self.run_api(self.window([(240000,[self.trade()])]),ingestion_ms=140000);self.assertEqual(result.minutes,());self.assertEqual(result.pending_observation_indices,(2,3))
 def test_backward_frame_utc_is_explicit_replay_model_refusal(self):self.no_accum(lambda:self.run_api(self.window([(150000,[self.trade()]),(140000,[self.trade('b')])]),ingestion_ms=160000))
 def test_first_seen_poc_tie_and_event_time_ohlc_order_are_preserved(self):
  result=self.run_api(self.window([(120000,[self.trade('later',time=45000,price='101',qty='1'),self.trade('earlier',time=30000,price='100',qty='1')])]))
  row=self.record(result);self.assertEqual((row['candle']['poc_price'],row['candle']['open'],row['candle']['close']),(101.,100.,101.))
 def test_input_records_and_parameters_detach_before_first_builder_math_call(self):
  import market_data.footprint_state as owner
  window=self.window();cfg=self.cfg();expected=self.api().materialize_observations_v12(window,**cfg);original=owner.price_bucket
  def mutate(*args,**kwargs):
   object.__setattr__(window[1],'payload_bytes',b'changed');cfg['instrument']['symbol']='ETHUSDT';cfg['units']['volume']='ETH';return original(*args,**kwargs)
  with patch.object(owner,'price_bucket',side_effect=mutate):actual=self.api().materialize_observations_v12(window,**cfg)
  self.assertEqual(actual,expected)
 def test_foreign_containers_bytes_and_tick_refuse_without_callbacks(self):
  a=self.api();calls=[]
  class Rows(list):
   def __iter__(self):calls.append('iter');return super().__iter__()
  class Blob(bytes):
   def __len__(self):calls.append('len');return super().__len__()
  class Tick(D):
   def __str__(self):calls.append('str');return super().__str__()
  for call in (lambda:self.run_api(Rows(self.window())),lambda:self.run_api((a.RawObservation(Blob(b'{}'),None),)),lambda:self.run_api(tick_size=Tick(1))):
   with self.assertRaises(ValueError):call()
  self.assertEqual(calls,[])
 def test_foreign_unused_unit_keys_and_parameter_leaves_refuse_callbacks(self):
  calls=[]
  class Key(str):
   def __eq__(self,value):calls.append('eq');return str.__eq__(self,value)
   __hash__=str.__hash__
  with self.assertRaises(ValueError):self.run_api(units={Key('price'):'USDT/BTC','volume':'BTC','turnover':'USDT'})
  self.assertEqual(calls,[])
 def test_window_and_payload_budgets_refuse_before_iteration_or_accumulation(self):
  a=self.api();window=self.window()
  with self.assertRaises(ValueError):self.run_api(window*6)
  with self.assertRaises(ValueError):self.run_api((a.RawObservation(window[0].observation_bytes,b'x'*1048577),))
 def test_archive_and_v1_are_explicitly_unsupported_not_silently_dropped(self):
  a=self.api();window=self.window();value=decode_observation(window[0].observation_bytes);value['schema']='market_data.raw-capture-observation.v1';raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
  with self.assertRaises(ValueError):self.run_api((a.RawObservation(raw,window[0].payload_bytes),))
  with self.assertRaises(ValueError):self.run_api(source_kind='ARCHIVE',endpoint='archive://bybit/linear')
 def test_candidate_bytes_lineage_and_replay_fingerprint_are_deterministic(self):
  window=self.window();a=self.run_api(window);b=self.run_api(window);self.assertEqual(a,b);self.assertEqual(a.minutes[0].record_fingerprint,self.record(a)['dataset_fingerprint']);self.assertEqual(a.minutes[0].frame_metadata_sha256s,(hashlib.sha256(window[1].observation_bytes).hexdigest(),));self.assertEqual(a.minutes[0].validated_metadata_sha256s,(hashlib.sha256(window[2].observation_bytes).hexdigest(),))
 def test_synthetic_source_uses_actual_decoder_kind_and_never_authenticates(self):
  changes={i:{'source_kind':'SYNTHETIC','endpoint':'synthetic://bybit/linear'} for i in range(3)};result=self.run_api(self.rewrite(self.window(),changes),source_kind='SYNTHETIC',endpoint='synthetic://bybit/linear');self.assertEqual(self.record(result)['status'],'PARTIAL');self.assertIs(self.record(result)['source_identity_verified'],False)
 def test_future_invalid_trade_conflict_and_missing_source_clock_refuse_whole_window(self):
  self.no_accum(lambda:self.run_api(self.window([(120000,[self.trade()]),(240000,[self.trade('bad',price='NaN')])])))
  with self.assertRaises(ValueError):self.run_api(producer_source_revision=None)

 def test_duplicate_validation_markers_are_bound_and_do_not_double_accumulate(self):
  a=self.api();window=self.window();meta=decode_observation(window[-1].observation_bytes);meta['observation_index']='4';meta['previous_metadata_sha256']=hashlib.sha256(window[-1].observation_bytes).hexdigest();duplicate=a.RawObservation(encode_observation(meta),None)
  result=self.run_api(window+(duplicate,));self.assertEqual(self.record(result)['candle']['trade_count'],2);self.assertEqual(len(result.minutes[0].validated_metadata_sha256s),2)
 def test_mixed_closed_and_open_executions_preserve_whole_shared_frame(self):
  window=self.window([(120000,[self.trade(),self.trade('open',time=90000)])]);result=self.run_api(window);self.assertEqual(len(result.minutes),1);self.assertEqual(self.record(result)['candle']['trade_count'],1);self.assertEqual(result.pending,window[1:]);self.assertEqual(len(result.pending_executions),1)
  replay=self.run_api(window,as_of_ms=240000,closed_through_ms=120000);self.assertEqual(len(replay.minutes),2);self.assertEqual(replay.minutes[0].record_bytes,result.minutes[0].record_bytes)
 def test_invalid_validated_later_frame_prevents_every_builder_add(self):
  window=self.window([(120000,[self.trade()]),(150000,[self.trade('invalid',qty='NaN')])]);self.no_accum(lambda:self.run_api(window))
 def test_first_parser_callback_cannot_rewrite_captured_later_observation(self):
  owner=self.api();window=self.window([(120000,[self.trade()]),(150000,[self.trade('later',time=50000,price='101')])]);cfg=self.cfg(ingestion_ms=160000);expected=owner.materialize_observations_v12(window,**cfg);original=owner.parse_trades;called=False
  def mutate(*args,**kwargs):
   nonlocal called
   if not called:called=True;object.__setattr__(window[3],'payload_bytes',b'changed');cfg['instrument']['symbol']='ETHUSDT'
   return original(*args,**kwargs)
  with patch.object(owner,'parse_trades',side_effect=mutate):actual=owner.materialize_observations_v12(window,**cfg)
  self.assertEqual(actual,expected)
 def test_source_epoch_tick_and_units_bind_replay_fingerprint_without_authentication(self):
  a=self.run_api();b=self.run_api(source_epoch='33333333-3333-4333-8333-333333333333');c=self.run_api(tick_size=D('0.5'))
  self.assertNotEqual(a.input_sha256,b.input_sha256);self.assertNotEqual(a.input_sha256,c.input_sha256);self.assertEqual(self.record(b)['source']['epoch'],'33333333-3333-4333-8333-333333333333');self.assertIs(self.record(b)['source_identity_verified'],False)
 def test_integer_ordinal_and_explicit_anchor_refuse_missing_prefix(self):
  a=self.api();window=self.window();self.no_accum(lambda:self.run_api(window[1:]))
  with self.assertRaises(ValueError):self.run_api(anchor=a.ObservationChainAnchor('11111111-1111-4111-8111-111111111111',True,None))
