import os
import time
from .provenance import digest

def read_snapshot(result, symbol, limit, before_ms, reader):
    if before_ms is None:
        before_ms = 9223372036854775807
    elif isinstance(before_ms,str) and before_ms.isdecimal() and len(before_ms)<=16:
        before_ms=int(before_ms)
    if type(before_ms) is not int or not 0 < before_ms <= 9223372036854775807:
        raise ValueError('invalid before_ms')
    if os.environ.get('TERMINAN_GRID_PROVENANCE_READ') != '1':
        return result
    try:
        records=reader(symbol,limit,before_ms)
        if not records:return result
        for r in records:
            import uuid
            uuid.UUID(r['source'].get('epoch',''))
            if r['api_version'] != {'major':1,'minor':1} or r['producer'] != 'bybit-cluster-grid':
                raise ValueError('unsupported snapshot')
            if any(type(r[k]) is not int for k in ('start_ms','end_ms','ingestion_ms','source_event_start_ms','source_event_end_ms')):
                raise ValueError('invalid snapshot times')
            if r['start_ms'] % 60000 or r['end_ms'] != r['start_ms']+59999 or not r['start_ms'] <= r['source_event_start_ms'] <= r['source_event_end_ms'] <= r['end_ms'] < r['ingestion_ms']:
                raise ValueError('invalid snapshot bounds')
            if digest({k:v for k,v in r.items() if k!='dataset_fingerprint'})!=r.get('dataset_fingerprint') or r.get('symbol')!=symbol:
                result['reason']='SNAPSHOT_INTEGRITY_FAILED';return result
        times=sorted(set(r['start_ms'] for r in records))
        if len(times)!=len(records):
            result['reason']='AMBIGUOUS_MINUTE_REVISIONS';return result
        expected=(times[-1]-times[0])//60000+1
        epochs={r['source'].get('epoch') for r in records}
        status,reason='PARTIAL','EXCHANGE_COMPLETENESS_UNATTESTED'
        if any(r['status']=='UNAVAILABLE' for r in records):status,reason='UNAVAILABLE','SOURCE_PROVENANCE_UNAVAILABLE'
        elif expected!=len(times) or len(epochs)!=1:status,reason='GAP','MISSING_MINUTES_OR_EPOCH_CHANGE'
        elif int(time.time()*1000)-max(r['source_event_end_ms'] for r in records)>120000:status,reason='STALE','FRESHNESS_WATERMARK_EXPIRED'
        result.update(status=status,reason=reason,api_version={'major':1,'minor':1},
            coverage={'expected_minutes':expected,'observed_minutes':len(times),'missing_minutes':expected-len(times)},
            freshness_utc_ms=max(r['source_event_end_ms'] or 0 for r in records),
            data_quality_status=status,producer_epochs=sorted(e or '' for e in epochs),
            dataset_fingerprint=digest(records),rows=records if status!='UNAVAILABLE' else [],
            next_before_ms=times[0],immutable=True,execution_authority=False)
        return result
    except Exception:
        result['reason']='SNAPSHOT_READ_UNAVAILABLE';return result
