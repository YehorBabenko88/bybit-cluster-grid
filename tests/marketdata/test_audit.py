"""Retained four range decisions, explicitly without completeness/readiness."""
import pytest

def assess(**kwargs):
 from market_data.history_range_audit import assess_declared_history_range
 return assess_declared_history_range(**kwargs)

def test_complete_active_history():
 result=assess(required_start_ms=100,required_end_ms=300,available_start_ms=100,available_end_ms=300,instrument_status='ACTIVE',recoverable=True)
 assert result['range_status']=='BOUNDARIES_PRESENT'
 assert result['coverage']=='UNKNOWN' and result['readiness']=='NOT_EVALUATED'

def test_unrecoverable_delisted_gap_is_partial():
 result=assess(required_start_ms=100,required_end_ms=300,available_start_ms=150,available_end_ms=250,instrument_status='DELISTED',recoverable=False)
 assert result['range_status']=='UNRECOVERABLE_PARTIAL_RANGE'
 assert result['coverage']=='UNKNOWN'

def test_missing_mandatory_dataset_is_insufficient():
 assert assess(required_start_ms=100,required_end_ms=300,available_start_ms=None,available_end_ms=None,instrument_status='ACTIVE',recoverable=True)['range_status']=='INSUFFICIENT_RANGE'

def test_history_before_listing_is_not_complete():
 assert assess(required_start_ms=100,required_end_ms=300,available_start_ms=200,available_end_ms=300,instrument_status='ACTIVE',recoverable=True,listed_at_ms=200)['range_status']=='INSUFFICIENT_RANGE'

@pytest.mark.parametrize('changes',[{'required_start_ms':True},{'required_end_ms':300.0},{'required_start_ms':-1},{'required_end_ms':253402300800000},{'required_start_ms':301},{'available_start_ms':True},{'available_end_ms':float('nan')},{'available_start_ms':400},{'listed_at_ms':True},{'recoverable':1},{'instrument_status':'unknown'},{'instrument_status':True}])
def test_bad_qualifications_refused(changes):
 args=dict(required_start_ms=100,required_end_ms=300,available_start_ms=100,available_end_ms=300,instrument_status='ACTIVE',recoverable=True);args.update(changes)
 with pytest.raises(ValueError):assess(**args)

def test_present_boundaries_never_assert_internal_contiguity_or_source_authentication():
 result=assess(required_start_ms=0,required_end_ms=180000,available_start_ms=0,available_end_ms=180000,instrument_status='ACTIVE',recoverable=True)
 assert result['range_status']=='BOUNDARIES_PRESENT'
 assert result['coverage_basis']=='DECLARED_BOUNDARIES_ONLY'
 assert result['coverage']=='UNKNOWN' and result['source_authenticity']=='NOT_EVALUATED'
 assert result['point_in_time_availability']=='UNKNOWN' and result['readiness']=='NOT_EVALUATED'
 assert 'download_status' not in result

def test_single_unknown_bound_and_recoverable_gap_are_insufficient():
 for lower,upper in ((None,300),(100,None),(150,250)):
  assert assess(required_start_ms=100,required_end_ms=300,available_start_ms=lower,available_end_ms=upper,instrument_status='ACTIVE',recoverable=True)['range_status']=='INSUFFICIENT_RANGE'


def test_oversized_status_refused_and_unknown_status_never_becomes_ready():
 with pytest.raises(ValueError):assess(required_start_ms=0,required_end_ms=1,available_start_ms=0,available_end_ms=1,instrument_status='X'*100000,recoverable=True)
 result=assess(required_start_ms=0,required_end_ms=1,available_start_ms=0,available_end_ms=1,instrument_status='UNKNOWN',recoverable=True)
 assert result['range_status']=='BOUNDARIES_PRESENT' and result['coverage']=='UNKNOWN'
 assert result['readiness']=='NOT_EVALUATED' and result['execution_authority'] is False and result['trading_authorized'] is False

def test_declared_maximum_utc_range_and_before_listing_refuse_completeness():
 result=assess(required_start_ms=0,required_end_ms=253402300799999,available_start_ms=0,available_end_ms=253402300799999,instrument_status='ACTIVE',recoverable=False)
 assert result['range_status']=='BOUNDARIES_PRESENT' and result['coverage']=='UNKNOWN'
 result=assess(required_start_ms=0,required_end_ms=300,available_start_ms=0,available_end_ms=300,instrument_status='ACTIVE',recoverable=True,listed_at_ms=200)
 assert result['range_status']=='INSUFFICIENT_RANGE' and result['reason']=='REQUEST_PRECEDES_DECLARED_LISTING'
