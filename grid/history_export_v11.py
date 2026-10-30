"""Opt-in v1.1 historical envelope. Receipt authenticity is provisioned externally.

dataset_id identifies immutable content; dataset_fingerprint additionally binds
as-of/admission request policy. Historical event times never imply availability.
"""
import copy
from .history_export import export_records, _read_records_postgres
from .provenance import digest


def dataset_content(envelope):
    q=envelope['request']
    return {'schema':'grid.dataset.v1.1','source':envelope['source'],
        'identity':{k:q[k] for k in ('venue','market_type','symbol','units')},
        'timeframe':'1m','representation':'historical_aggregate',
        'evidence_class':envelope['evidence_class'],'rows':envelope['rows'],
        'source_receipts':envelope['source_receipts']}


def export_records_v11(records,request,trust):
    records,request,trust=copy.deepcopy((records,request,trust))
    envelope=export_records(records,request,trust)
    envelope.pop('dataset_fingerprint')
    envelope['schema']='grid.history.v1.1'
    try:
        for raw,row in zip(records,envelope['rows']):
            a,b=raw['source_event_start_ms'],raw['source_event_end_ms']
            if type(a) is not int or type(b) is not int or not row['event_start_ms']<=a<=b<row['event_end_ms']:
                raise ValueError('SOURCE_EVENT_CLOCK')
            row.update(source_event_start_ms=a,source_event_end_ms=b)
            receipt=trust['receipts'][row['revision']]
            watermark=receipt['watermark_ms']
            if type(watermark) is not int or not row['event_end_ms']<=watermark<=row['available_at_ms']:
                raise ValueError('WATERMARK_AFTER_AVAILABILITY')
            row['watermark_ms']=watermark
            row['source_receipt_hash']=trust['receipt_pins'][row['revision']]
        envelope['watermark_ms']=max(r['watermark_ms'] for r in envelope['rows'])
        envelope['dataset_id']=digest(dataset_content(envelope))
        envelope['dataset_fingerprint']=digest(envelope)
        return envelope
    except (KeyError,TypeError,OverflowError) as exc:
        raise ValueError('TIMED_HISTORY_UNAVAILABLE') from exc


def read_postgres_v11(conn,request,trust):
    try:records=_read_records_postgres(conn,request)
    except Exception:raise ValueError('SOURCE_READ_UNAVAILABLE') from None
    return export_records_v11(records,request,trust)
