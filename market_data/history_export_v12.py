"""Opt-in explicit-turnover history v1.2; pure, no reader/writer or endpoint.

Receipts and units are independently provisioned declarations, never inferred
from old candles, event-end clocks, rounded profiles or provider backfill tables.
"""
from .history_contract import (_snapshot_json,_clock,_units,_version,_record,
    TURNOVER_BASIS,AVAILABILITY_BASIS,FINANCIAL_ENCODING)
from .history_export import _export_records,MAX_ROWS
from .history_export_v11 import _timed_rows,_dataset_content
from .provenance import digest

def export_records_v12(records,request,trust):
    """Export only new explicit minute records and matching versioned receipts.

    Legacy v1/v1.1 records remain immutable and unavailable to this contract.
    Availability remains caller-declared, not commit/PIT or completeness proof.
    """
    try:
        if (type(records) is not list and type(records) is not tuple) or not 1<=len(records)<=MAX_ROWS:raise ValueError('TURNOVER_HISTORY_BOUNDED_RECORDS_REQUIRED')
        records,request,trust=_snapshot_json((records,request,trust))
        if type(request) is not dict or type(trust) is not dict:raise ValueError('TURNOVER_HISTORY_LITERAL_REQUEST_TRUST_REQUIRED')
        if request['schema']!='market_data.history.request.v1.2' or trust['schema']!='market_data.history.trust.v1.2':raise ValueError('TURNOVER_HISTORY_VERSION_REQUIRED')
        units=_units(request['units'])
        if type(trust['receipts']) is not dict or type(trust['receipt_pins']) is not dict:raise ValueError('TURNOVER_HISTORY_RECEIPT_MAP_REQUIRED')
        fingerprints={row['dataset_fingerprint'] for row in records}
        if len(fingerprints)!=len(records) or set(trust['receipts'])!=fingerprints or set(trust['receipt_pins'])!=fingerprints:raise ValueError('TURNOVER_HISTORY_EXACT_RECEIPT_ROSTER_REQUIRED')
        for record in records:
            _record(record)
            if record['units']!=units:raise ValueError('TURNOVER_HISTORY_RECORD_UNITS_MISMATCH')
            receipt=trust['receipts'][record['dataset_fingerprint']]
            if type(receipt) is not dict or receipt['schema']!='market_data.history.receipt.v1.2' or receipt['dataset_schema']!='market_data.dataset.v1.2':raise ValueError('TURNOVER_HISTORY_RECEIPT_VERSION_REQUIRED')
            _version(receipt['record_api_version'])
            if receipt['turnover_basis']!=TURNOVER_BASIS or receipt['units']!=units:raise ValueError('TURNOVER_HISTORY_RECEIPT_DECLARATION_MISMATCH')
            if _clock(receipt['available_at_ms'])!=record['available_at_ms']:raise ValueError('TURNOVER_HISTORY_RECEIPT_AVAILABILITY_MISMATCH')
        envelope=_export_records(records,request,trust,version='v1.2')
        envelope.pop('dataset_fingerprint')
        envelope.update(schema='market_data.history.v1.2',turnover_basis=TURNOVER_BASIS,
            availability_basis=AVAILABILITY_BASIS,financial_encoding=FINANCIAL_ENCODING,
            source_authentication='NOT_EVALUATED')
        _timed_rows(records,envelope,trust)
        envelope['dataset_id']=digest(_dataset_content(envelope,'market_data.dataset.v1.2'))
        envelope['dataset_fingerprint']=digest(envelope)
        return envelope
    except (KeyError,TypeError,OverflowError) as exc:raise ValueError('TURNOVER_HISTORY_UNAVAILABLE') from exc
