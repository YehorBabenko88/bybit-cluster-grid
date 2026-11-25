"""Pure canonical projection/index obligations; no owner grants or IO adapters."""
import copy,hashlib,json,unittest
from pathlib import Path
from unittest.mock import patch
from test_gateway_query_fixture_codec import fixture,c3
import test_gateway_query_preparation as preparation

def context_for(raw):
 root=json.loads(raw)
 context={key:root[key] for key in ('manifest_revision','data_schema_sha256','segments_root_sha256','coverage_root_sha256','dependencies_root_sha256')}
 context.update(manifest_sha256=hashlib.sha256(raw).hexdigest(),dataset_id=root['lineage']['dataset_id'],instrument_id=root['lineage']['instrument_id'],lineage_sha256=hashlib.sha256(c3(root['lineage'])).hexdigest(),source_class='SYNTHETIC')
 return context

class ProjectionTests(unittest.TestCase):
 def setUp(self):
  import market_data.gateway_query as m
  self.m=m;self.root,self.objects=fixture();self.context=context_for(self.root)
 def prepared(self,start='0',end='180000',cut='180000'):
  helper=preparation.PreparationTests();helper.module=self.m;request=helper.request()
  request['knowledge_cut']={'manifest_sha256':self.context['manifest_sha256'],'manifest_revision':self.context['manifest_revision']}
  request['range']={'start_ms':start,'end_ms':end};request['event_cut_ms']=cut
  return self.m.prepare_query(c3(request))
 def project(self,**changes):
  args=dict(context=self.context,manifest_bytes=self.root,objects_by_sha256=self.objects);args.update(changes)
  return self.m.project_query(self.prepared(),**args)
 def test_single_reference_is_bounded_immutable_and_selects_actual_rows(self):
  ref=self.m.decode_query_segment_index(self.objects[self.context['segments_root_sha256']],context=self.context)
  self.assertIn(ref.sha256,self.objects);self.assertEqual(ref.bytes,len(self.objects[ref.sha256]));self.assertEqual(ref.row_count,2)
  with self.assertRaises((AttributeError,TypeError)):ref.sha256='e'*64
 def test_projection_keeps_both_rows_and_explicit_gap_without_authority(self):
  result=self.project()
  self.assertEqual([r[0] for r in result['rows']],['0','120000'])
  self.assertEqual([c['disposition'] for c in result['cells']],['PRESENT','GAP','PRESENT'])
  self.assertFalse(result['execution_authority']);self.assertFalse(result['native_authenticated'])
  self.assertEqual(result['session_classification'],'NOT_EVALUATED_BY_PURE_DATA')
  self.assertEqual(result['provider_coverage'],'UNKNOWN')
 def test_requested_subset_is_not_latest_manifest_alias(self):
  result=self.m.project_query(self.prepared('0','120000'),context=self.context,manifest_bytes=self.root,objects_by_sha256=self.objects)
  self.assertEqual([r[0] for r in result['rows']],['0'])
  self.assertEqual([c['disposition'] for c in result['cells']],['PRESENT','GAP'])
  self.assertEqual(result['dataset_revision'],'2');self.assertEqual(result['manifest_revision'],'1')
 def test_no_generic_root_manifest_parse_or_authentication(self):
  opaque=b'opaque already-decoded Root manifest fixture'
  context=copy.deepcopy(self.context);context['manifest_sha256']=hashlib.sha256(opaque).hexdigest()
  helper=preparation.PreparationTests();helper.module=self.m;request=helper.request();request['knowledge_cut']['manifest_sha256']=context['manifest_sha256']
  prepared=self.m.prepare_query(c3(request))
  result=self.m.project_query(prepared,context=context,manifest_bytes=opaque,objects_by_sha256=self.objects)
  self.assertFalse(result['execution_authority']);self.assertEqual(result['publication'],'UNPROVEN')
 def test_request_context_mismatch_refuses_and_original_inputs_detached(self):
  before=copy.deepcopy(self.context);objects=dict(self.objects)
  changed=copy.deepcopy(self.context);changed['manifest_revision']='2'
  with self.assertRaises(self.m.QueryFormatError):self.project(context=changed)
  result=self.project();result['rows'][0][1]='999';result['request']['instrument_id']['symbol']='OTHER'
  self.assertEqual(self.context,before);self.assertEqual(self.objects,objects);self.assertEqual(self.project()['rows'][0][1],'100')
 def test_bad_reference_and_unknown_closed_context_refused(self):
  raw=self.objects[self.context['segments_root_sha256']]
  for changes in ({'source_class':'ACTUAL'},{'unexpected':'x'},{'manifest_revision':True},{'instrument_id':None}):
   ctx=copy.deepcopy(self.context);ctx.update(changes)
   with self.assertRaises(self.m.QueryFormatError):self.m.decode_query_segment_index(raw,context=ctx)
  with self.assertRaises(self.m.QueryFormatError):self.m.decode_query_segment_index(raw+b' ',context=self.context)
 def test_old_wire_profile_never_accepted_as_alias(self):
  helper=preparation.PreparationTests();helper.module=self.m;request=helper.request();request['schema']='grid.gateway.ohlcv-query.v1-review2'
  with self.assertRaises(self.m.QueryFormatError):self.m.prepare_query(c3(request))
  for invalid_cut in (None,False,''):
   value=helper.request();value['event_cut_ms']=invalid_cut
   with patch.object(self.m,'query_minute_grid_ms',wraps=self.m.query_minute_grid_ms) as kernel:
    with self.assertRaises(self.m.QueryFormatError):self.m.prepare_query(c3(value))
    self.assertEqual(kernel.call_count,0)
  value=helper.request();value.pop('event_cut_ms')
  with self.assertRaises(self.m.QueryFormatError):self.m.prepare_query(c3(value))
 def test_index_oversize_refuses_before_hash(self):
  with patch.object(self.m.hashlib,'sha256',wraps=hashlib.sha256) as hashing:
   with self.assertRaises(self.m.QueryFormatError):self.m.decode_query_segment_index(b' '*16385,context=self.context)
   self.assertEqual(hashing.call_count,0)
 def test_huge_unknown_context_refuses_before_iteration_or_hash(self):
  ctx={str(i):None for i in range(100000)}
  raw=self.objects[self.context['segments_root_sha256']]
  with patch.object(self.m.hashlib,'sha256',wraps=hashlib.sha256) as hashing:
   with self.assertRaises(self.m.QueryFormatError):self.m.decode_query_segment_index(raw,context=ctx)
   self.assertEqual(hashing.call_count,0)

 def test_exact_decimal_strings_and_hostile_context_survive_projection(self):
  from decimal import localcontext
  directory=Path(__file__).resolve().parent/'query_fixtures'
  records={name:json.loads((directory/(name+'.canonical.json')).read_bytes()) for name in ('rows','segment-index','coverage','dependencies','manifest')}
  rows,index,coverage,dependencies,manifest=[records[name] for name in ('rows','segment-index','coverage','dependencies','manifest')]
  price='100.0000000000000000001';tiny='0.'+'0'*69+'1'
  rows['rows'][0][1]=price;rows['rows'][0][5]=tiny;rows['rows'][0][6]=tiny
  rows_raw=c3(rows);index['segments'][0].update(sha256=hashlib.sha256(rows_raw).hexdigest(),bytes=str(len(rows_raw)))
  index_raw=c3(index);coverage['segments_root_sha256']=hashlib.sha256(index_raw).hexdigest();coverage_raw=c3(coverage)
  descriptor=(directory/'data-schema.canonical.json').read_bytes()
  dependencies['objects']=[dict(role=role,sha256=hashlib.sha256(raw).hexdigest(),bytes=str(len(raw))) for role,raw in [('data_schema',descriptor),('rows',rows_raw),('segment_index',index_raw),('coverage',coverage_raw)]]
  dependencies_raw=c3(dependencies);manifest.update(segments_root_sha256=hashlib.sha256(index_raw).hexdigest(),coverage_root_sha256=hashlib.sha256(coverage_raw).hexdigest(),dependencies_root_sha256=hashlib.sha256(dependencies_raw).hexdigest())
  self.root=c3(manifest);self.context=context_for(self.root);self.objects={hashlib.sha256(raw).hexdigest():raw for raw in (descriptor,rows_raw,index_raw,coverage_raw,dependencies_raw)}
  with localcontext() as context:
   context.prec=2
   for signal in context.traps:context.traps[signal]=True
   context.clear_flags();before=context.copy()
   result=self.project()
   self.assertEqual(result['rows'][0][1],price);self.assertEqual(result['rows'][0][5],tiny)
   self.assertEqual(result['rows'][0][6],tiny);self.assertEqual(context.flags,before.flags);self.assertEqual(context.prec,before.prec)

 def test_hostile_row_width_refuses_before_json_loads(self):
  raw=c3({'rows':[[] for _ in range(160000)]})
  self.assertLessEqual(len(raw),524288)
  with patch.object(self.m.json,'loads',wraps=json.loads) as loads:
   with self.assertRaises(self.m.QueryFormatError):self.m._fixture_json(raw,524288)
   self.assertEqual(loads.call_count,0)
 def test_request_extra_scalar_fields_refuse_before_json_loads(self):
  helper=preparation.PreparationTests();helper.module=self.m;request=helper.request()
  request.update({('extra'+str(i)):'x' for i in range(1000)});raw=c3(request)
  self.assertLess(len(raw),32768)
  with patch.object(self.m.json,'loads',wraps=json.loads) as loads:
   with self.assertRaises(self.m.QueryFormatError):self.m.prepare_query(raw)
   self.assertEqual(loads.call_count,0)
 def test_container_field_column_budgets_and_escaped_strings(self):
  hostile=[c3({'rows':[[[] for _ in range(7)] for _ in range(210)]}),c3({str(i):'x' for i in range(17)}),c3({'rows':[['x']*8]}),b'{"\\u0072ows":[]}']
  for raw in hostile:
   with patch.object(self.m.json,'loads',wraps=json.loads) as loads:
    with self.assertRaises(self.m.QueryFormatError):self.m._fixture_json(raw,524288)
    self.assertEqual(loads.call_count,0)
  value={'text':(','*5000)+'[]{}"\\end'};raw=c3(value)
  self.assertEqual(self.m._fixture_json(raw,524288),value)
 def test_exact_1440_rows_and_cells_remain_valid(self):
  directory=Path(__file__).resolve().parent/'query_fixtures'
  records={name:json.loads((directory/(name+'.canonical.json')).read_bytes()) for name in ('rows','segment-index','coverage','dependencies','manifest')}
  rows,index,coverage,dependencies,manifest=[records[name] for name in ('rows','segment-index','coverage','dependencies','manifest')]
  grid=self.m.query_minute_grid_ms(0,86400000,event_cut_ms=86400000)
  self.assertEqual(len(grid),1440)
  template=list(rows['rows'][0]);rows['rows']=[[str(lower),*template[1:]] for lower,_ in grid]
  index['declared_range']={'start_ms':'0','end_ms':'86400000'};index['segments'][0]['row_count']='1440'
  rows_raw=c3(rows);index['segments'][0].update(sha256=hashlib.sha256(rows_raw).hexdigest(),bytes=str(len(rows_raw)))
  index_raw=c3(index);coverage['segments_root_sha256']=hashlib.sha256(index_raw).hexdigest();coverage['declared_range']=dict(index['declared_range'])
  coverage['cells']=[dict(start_ms=str(lower),end_ms=str(upper),disposition='PRESENT',reason='FIXTURE_GENERATED',recoverability='NOT_APPLICABLE') for lower,upper in grid];coverage_raw=c3(coverage)
  descriptor=(directory/'data-schema.canonical.json').read_bytes()
  dependencies['objects']=[dict(role=role,sha256=hashlib.sha256(raw).hexdigest(),bytes=str(len(raw))) for role,raw in [('data_schema',descriptor),('rows',rows_raw),('segment_index',index_raw),('coverage',coverage_raw)]]
  dependencies_raw=c3(dependencies);manifest.update(segments_root_sha256=hashlib.sha256(index_raw).hexdigest(),coverage_root_sha256=hashlib.sha256(coverage_raw).hexdigest(),dependencies_root_sha256=hashlib.sha256(dependencies_raw).hexdigest())
  self.root=c3(manifest);self.context=context_for(self.root);self.objects={hashlib.sha256(raw).hexdigest():raw for raw in (descriptor,rows_raw,index_raw,coverage_raw,dependencies_raw)}
  result=self.m.project_query(self.prepared(end='86400000',cut='86400000'),context=self.context,manifest_bytes=self.root,objects_by_sha256=self.objects)
  self.assertEqual(len(result['rows']),1440);self.assertEqual(len(result['cells']),1440)
  self.assertEqual(result['rows'][-1][0],'86340000');self.assertEqual(result['cells'][-1]['end_ms'],'86400000')
