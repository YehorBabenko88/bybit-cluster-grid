"""Conservative caller-declared range decisions, never completeness or readiness.

Retains the useful historical range classifier from Strattester, without its
unsafe COMPLETE_HISTORY conclusion from only min/max timestamps. Actual gap
inspection remains the independent HistoricalMarketReader coverage contract.
"""
from .timestamp_codec import epoch_milliseconds

_STATUSES=frozenset(('PRE_LISTING','ACTIVE','SUSPENDED','MISSING','DELISTED','UNKNOWN'))

def _clock(value):
    if type(value) is not int:raise ValueError('strict declared integer millisecond clock required')
    return epoch_milliseconds(value)

def assess_declared_history_range(*,required_start_ms,required_end_ms,
                                  available_start_ms,available_end_ms,
                                  instrument_status,recoverable,listed_at_ms=None):
    """Classify declared boundaries only; no source, download or gap assertion."""
    required_start_ms=_clock(required_start_ms);required_end_ms=_clock(required_end_ms)
    if required_start_ms>required_end_ms:raise ValueError('reversed required range')
    if available_start_ms is not None:available_start_ms=_clock(available_start_ms)
    if available_end_ms is not None:available_end_ms=_clock(available_end_ms)
    if available_start_ms is not None and available_end_ms is not None and available_start_ms>available_end_ms:
        raise ValueError('reversed available range')
    if listed_at_ms is not None:listed_at_ms=_clock(listed_at_ms)
    if type(instrument_status) is not str or len(instrument_status)>16 or instrument_status not in _STATUSES:
        raise ValueError('explicit declared instrument lifecycle status required')
    if type(recoverable) is not bool:raise ValueError('strict declared recoverability required')
    if available_start_ms is None or available_end_ms is None:
        state='INSUFFICIENT_RANGE';reason='AVAILABLE_RANGE_UNKNOWN'
    elif listed_at_ms is not None and required_start_ms<listed_at_ms:
        state='INSUFFICIENT_RANGE';reason='REQUEST_PRECEDES_DECLARED_LISTING'
    elif available_start_ms<=required_start_ms and available_end_ms>=required_end_ms:
        state='BOUNDARIES_PRESENT';reason='REQUIRED_BOUNDARIES_PRESENT'
    elif instrument_status=='DELISTED' and recoverable is False:
        state='UNRECOVERABLE_PARTIAL_RANGE';reason='DELISTED_RANGE_UNRECOVERABLE'
    else:
        state='INSUFFICIENT_RANGE';reason='REQUIRED_RANGE_NOT_SPANNED'
    return dict(schema='market_data.declared-history-range.v1',range_status=state,reason=reason,
                required_start_ms=required_start_ms,required_end_ms=required_end_ms,
                available_start_ms=available_start_ms,available_end_ms=available_end_ms,
                instrument_status=instrument_status,recoverable=recoverable,listed_at_ms=listed_at_ms,
                coverage='UNKNOWN',coverage_basis='DECLARED_BOUNDARIES_ONLY',
                source_authenticity='NOT_EVALUATED',point_in_time_availability='UNKNOWN',
                readiness='NOT_EVALUATED',execution_authority=False,trading_authorized=False)
