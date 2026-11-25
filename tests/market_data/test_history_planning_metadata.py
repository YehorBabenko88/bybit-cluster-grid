"""Declared history metadata and actual Math window helper; no I/O."""
from dataclasses import FrozenInstanceError
import pytest

def module():
 from market_data import history_planning
 return history_planning

def test_metadata_is_closed_detached_immutable_and_not_source_authority():
 m=module();raw=dict(symbol='BTCUSDT',launchTime='60000',fundingInterval='480',supportsFunding=True)
 item=m.declare_history_instrument(raw);raw['launchTime']='900000'
 assert item.launch_ms==60000 and item.funding_interval_minutes==480
 assert item.schema=='market_data.history-instrument-declaration.v1'
 assert item.source_authenticity=='NOT_EVALUATED'
 with pytest.raises(FrozenInstanceError):item.launch_ms=1

@pytest.mark.parametrize('changes',[{'symbol':True},{'symbol':'xusdt'},{'launchTime':True},{'launchTime':1.0},{'launchTime':'01'},{'launchTime':-1},{'launchTime':'253402300800000'},{'fundingInterval':False},{'fundingInterval':'0'},{'fundingInterval':'1.5'},{'fundingInterval':'9007199254740992'},{'supportsFunding':1},{'supportsOpenInterest':'false'},{'deliveryTime':True},{'deliveryTime':'600000','delistTime':'900000'},{'password':'synthetic'}])
def test_invalid_metadata_refuses_before_planning(changes):
 raw=dict(symbol='BTCUSDT',launchTime='0');raw.update(changes)
 with pytest.raises(ValueError):module().declare_history_instrument(raw)

def test_top_level_cardinality_refuses_without_large_copy():
 with pytest.raises(ValueError):module().declare_history_instrument({str(i):None for i in range(10000)})

def test_unknown_funding_cadence_is_unplanned_not_an_invented_480_minutes():
 m=module();item=m.declare_history_instrument(dict(symbol='BTCUSDT',launchTime='0',supportsFunding=True))
 plan=m.plan_history_requests(item,end_ms=1000000)
 assert 'funding' not in {r.dataset for r in plan.requests}
 assert ('funding','CADENCE_UNKNOWN') in plan.unplanned
 assert plan.coverage=='UNKNOWN' and plan.readiness=='NOT_EVALUATED'
 assert plan.source_authenticity=='NOT_EVALUATED' and plan.point_in_time_availability=='UNKNOWN'

def test_zero_delivery_uses_explicit_delist_and_no_finality_is_claimed():
 m=module();item=m.declare_history_instrument(dict(symbol='BTCUSDT',launchTime='0',deliveryTime='0',delistTime='600000'))
 plan=m.plan_history_requests(item,end_ms=900000)
 assert all(r.end_ms<=600000 for r in plan.requests)
 assert plan.requested_end_ms==900000 and plan.effective_end_ms==600000
 assert plan.instrument is item and 'delistTime' in item.declared_fields
 assert all(r.coverage=='UNKNOWN' and r.readiness=='NOT_EVALUATED' for r in plan.requests)
 assert plan.execution_authority is False and plan.trading_authorized is False

def test_multiday_cadence_is_not_silently_capped_at_1440():
 m=module();item=m.declare_history_instrument(dict(symbol='BTCUSDT',launchTime='0',fundingInterval='2880',supportsFunding=True))
 plan=m.plan_history_requests(item,end_ms=172800000)
 funding=next(r for r in plan.requests if r.dataset=='funding')
 assert (funding.start_ms,funding.end_ms,funding.timeframe)==(0,172800000,'2880m')


def test_direct_typed_declaration_rejects_string_cadence_and_boolean_clock():
 m=module()
 for changes in ({'funding_interval_minutes':'480'},{'launch_ms':True}):
  with pytest.raises(ValueError):m.HistoryInstrumentDeclaration('BTCUSDT',**changes)

def test_maximum_numeric_cadence_budget_is_explicit_not_provider_support():
 m=module();item=m.declare_history_instrument(dict(symbol='BTCUSDT',launchTime='0',fundingInterval='9007199254740991',supportsFunding=True))
 plan=m.plan_history_requests(item,end_ms=1)
 request=next(r for r in plan.requests if r.dataset=='funding')
 assert request.start_ms==request.end_ms==0 and plan.coverage=='UNKNOWN'

def test_math_delegation_preserves_hostile_caller_decimal_context():
 from decimal import localcontext
 m=module();item=m.declare_history_instrument(dict(symbol='BTCUSDT',launchTime='61000',fundingInterval='8',deliveryTime='899999'))
 with localcontext() as ctx:
  ctx.prec=2
  for signal in ctx.traps:ctx.traps[signal]=True
  before=dict(ctx.flags);plan=m.plan_history_requests(item,end_ms=999999)
  assert next(r for r in plan.requests if r.dataset=='funding').start_ms==480000
  assert dict(ctx.flags)==before
