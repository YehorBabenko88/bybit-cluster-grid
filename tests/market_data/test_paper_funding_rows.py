"""Per-row assessments retain earlier unknowns without changing the packet."""
import copy
import pytest
from test_paper_inputs import rows,row,funding,request,hash_value
from market_data.paper_inputs import export_paper_inputs,ExportBlocked

def assess(packet, **kwargs):
 from market_data.paper_inputs import assess_paper_funding_rows
 return assess_paper_funding_rows(packet,**kwargs)

def test_earlier_unknown_not_borrowing_latest_known_status():
 records=rows();records[-1]['payload'].pop('_field_observations')
 records.append(row(4,'derivatives_ticker',funding(),1999900,1999950))
 packet=export_paper_inputs(records,request());before=copy.deepcopy(packet)
 assert packet['funding_status']=='KNOWN_SOURCE_FIELDS'
 result=assess(packet,now_ms=2000001)
 assert [r['row_id'] for r in result]==[3,4]
 assert [r['funding_status'] for r in result]==['UNAVAILABLE','KNOWN_SOURCE_FIELDS']
 assert result[0]['field_states']=={k:'PROOF_MISSING' for k in funding(False)}
 assert packet==before
 assert all(r['source_request_sha256']==hash_value(packet['request']) for r in result)
 assert [r['row_sha256'] for r in result]==[r['row_sha256'] for r in packet['rows'][-2:]]

def test_explicit_null_and_omission_remain_distinct():
 records=rows();records[-1]['payload']={'funding_rate':None}
 # Keep the actual declared same connection; no synthetic source qualification.
 from test_paper_inputs import context
 records[-1]['payload']['_producer_connection']=context()
 packet=export_paper_inputs(records,request());result=assess(packet,now_ms=2000001)[0]
 assert result['fields']=={'funding_rate':None}
 assert result['field_observations']=={}
 assert result['field_states']=={'funding_rate':'EXPLICIT_UNKNOWN','funding_interval_hour':'OMITTED','next_funding_time':'OMITTED'}
 assert result['funding_status']=='UNAVAILABLE'

def test_use_time_staleness_each_row_and_detached_return():
 packet=export_paper_inputs(rows(),request());before=copy.deepcopy(packet)
 known=assess(packet,now_ms=2009800)[0]
 assert known['funding_status']=='KNOWN_SOURCE_FIELDS'
 assert all(v=='KNOWN_SOURCE_FIELD' for v in known['field_states'].values())
 stale=assess(packet,now_ms=2009801)[0]
 assert stale['funding_status']=='UNAVAILABLE' and all(v=='STALE' for v in stale['field_states'].values())
 known['field_observations']['funding_rate']['event_ms']=1
 known['fields']['funding_rate']='9'
 assert packet==before

@pytest.mark.parametrize('now',[True,1999999,253402300800000])
def test_bad_use_clock_refused(now):
 with pytest.raises(ExportBlocked):assess(export_paper_inputs(rows(),request()),now_ms=now)

def test_empty_and_producer_unknown_never_known():
 assert assess(export_paper_inputs([],request()),now_ms=2000001)==()
 records=rows()
 for r in records:r['payload'].pop('_producer_connection')
 result=assess(export_paper_inputs(records,request()),now_ms=2000001)
 assert result[0]['funding_status']=='UNAVAILABLE'


def test_explicit_unknown_before_known_and_latest_unknown_do_not_cross_contaminate():
 records=rows();records[-1]['payload']['funding_rate']=None
 records[-1]['payload'].pop('_field_observations')
 records.append(row(4,'derivatives_ticker',funding(),1999900,1999950))
 packet=export_paper_inputs(records,request());result=assess(packet,now_ms=2000001)
 assert result[0]['field_states']['funding_rate']=='EXPLICIT_UNKNOWN'
 assert [r['funding_status'] for r in result]==['UNAVAILABLE','KNOWN_SOURCE_FIELDS']
 records=rows()+[row(4,'derivatives_ticker',{'funding_rate':None},1999900,1999950)]
 packet=export_paper_inputs(records,request());result=assess(packet,now_ms=2000001)
 assert packet['funding_status']=='UNAVAILABLE'
 assert [r['funding_status'] for r in result]==['KNOWN_SOURCE_FIELDS','UNAVAILABLE']

def test_hostile_decimal_flags_and_top_map_bound_unchanged():
 from decimal import localcontext
 packet=export_paper_inputs(rows(),request())
 with localcontext() as ctx:
  ctx.prec=2
  for signal in ctx.traps:ctx.traps[signal]=True
  flags=dict(ctx.flags)
  assert assess(packet,now_ms=2000001)[0]['funding_status']=='KNOWN_SOURCE_FIELDS'
  assert dict(ctx.flags)==flags
 bad={str(i):None for i in range(10000)}
 with pytest.raises(ExportBlocked,match='PAPER_PACKET'):assess(bad,now_ms=2000001)
