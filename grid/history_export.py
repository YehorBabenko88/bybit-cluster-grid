"""Opt-in bounded immutable historical export; no connection creation or DDL.

Trust is supplied by the operator, independently of records. Receipt pins are
not authentication: provisioning authenticated HISTORICAL receipts is external.
Existing ingestion_ms is deliberately never treated as feature availability.
"""
import copy
import math
from .provenance import canonical, digest

MAX_ROWS=2000
MAX_BYTES=8*1024*1024


def export_records(records, request, trust):
    try:
        q=copy.deepcopy(request); t=copy.deepcopy(trust)
        if q['schema']!='grid.history.request.v1':raise ValueError('SCHEMA')
        for key in ('start_ms','end_ms','as_of_ms','max_age_ms'):
            if type(q[key]) is not int or not 0<=q[key]<=2**53-1:raise ValueError('TIME')
        start,end=q['start_ms'],q['end_ms']; count=(end-start)//60000
        if start%60000 or end%60000 or not 1<=count<=MAX_ROWS:raise ValueError('BOUNDS')
        if q['as_of_ms']<end or q['as_of_ms']-end>q['max_age_ms']:raise ValueError('STALE')
        if len(records)!=count or len(canonical(records))>MAX_BYTES:raise ValueError('COVERAGE')
        if t['evidence_class'] not in ('SYNTHETIC','HISTORICAL'):raise ValueError('EVIDENCE')
        if not all(isinstance(t[k],str) and t[k] for k in ('identity','source_revision','epoch')):raise ValueError('SOURCE')
        if not all(isinstance(q[k],str) and q[k] for k in ('venue','market_type','symbol')):raise ValueError('IDENTITY')
        if set(q['units'])!={'price','volume'} or not all(isinstance(v,str) and v for v in q['units'].values()):raise ValueError('UNITS')
        out=[]; receipt_hashes=[]
        for i,r in enumerate(records):
            fp=r['dataset_fingerprint']
            if digest({k:v for k,v in r.items() if k!='dataset_fingerprint'})!=fp:raise ValueError('INTEGRITY')
            s=r['source']; a=t['receipts'][fp]
            if t['receipt_pins'][fp]!=digest(a) or a['fingerprint']!=fp:raise ValueError('RECEIPT')
            if any(s[k]!=t[k] for k in ('identity','source_revision','epoch')):raise ValueError('SOURCE')
            if (r['symbol']!=q['symbol'] or s['market_type']!=q['market_type'] or a['venue']!=q['venue']
                or a['units']!=q['units'] or a['evidence_class']!=t['evidence_class']):raise ValueError('IDENTITY_OR_UNITS')
            lo=start+i*60000; hi=lo+60000
            if r['start_ms']!=lo or r['end_ms']!=hi-1 or r['representation']!='historical_aggregate':raise ValueError('COVERAGE')
            if r['status']=='UNAVAILABLE' or a['complete'] is not True:raise ValueError('INCOMPLETE')
            if any(type(a[k]) is not int for k in ('available_at_ms','watermark_ms')):raise ValueError('AVAILABILITY')
            if not hi<=a['available_at_ms']<=q['as_of_ms'] or not hi<=a['watermark_ms']<=q['as_of_ms']:raise ValueError('AVAILABILITY')
            c=r['candle']; vals=[c[k] for k in ('open','high','low','close','buy_volume','sell_volume')]
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in vals):raise ValueError('NUMERIC')
            if not 0<c['low']<=min(c['open'],c['close'])<=max(c['open'],c['close'])<=c['high'] or min(c['buy_volume'],c['sell_volume'])<0:raise ValueError('OHLCV')
            volume=c['buy_volume']+c['sell_volume']
            if not math.isfinite(volume):raise ValueError('VOLUME')
            out.append({**{k:c[k] for k in ('open','high','low','close')},'volume':volume,
              'event_start_ms':lo,'event_end_ms':hi,'available_at_ms':a['available_at_ms'],'revision':fp})
            receipt_hashes.append(t['receipt_pins'][fp])
        envelope={'schema':'grid.history.v1','request':q,'source':{k:t[k] for k in ('identity','source_revision','epoch')},
            'evidence_class':t['evidence_class'],'rows':out,'source_receipts':receipt_hashes,
            'execution_authority':False,'trading_authorized':False}
        envelope['dataset_fingerprint']=digest(envelope)
        return envelope
    except (KeyError,TypeError,OverflowError) as exc:
        raise ValueError('HISTORY_UNAVAILABLE') from exc


def _read_records_postgres(conn, request, *, revisions=None):
    """Caller supplies a fresh dedicated read-only connection; owns rollback/close.

    Transaction setting fails if caller already issued a query. Oversize records
    are returned as NULL by SQL, so Python never materializes unbounded JSON.
    No credentials, connection or production schema are modified here.
    """
    # Validate request bounds before issuing any SQL, including malformed inputs.
    q=request
    for k in ('start_ms','end_ms'):
        if type(q.get(k)) is not int or q[k]<0 or q[k]%60000:raise ValueError('BOUNDS')
    if not 1<=(q['end_ms']-q['start_ms'])//60000<=MAX_ROWS:raise ValueError('BOUNDS')
    if revisions is not None and (type(revisions) is not list or
        not 1<=len(revisions)<=MAX_ROWS or any(type(v) is not str or len(v)!=64 or
        any(c not in '0123456789abcdef' for c in v) for v in revisions)):
        raise ValueError('REVISION_PINS')
    revision_sql = '' if revisions is None else ' AND fingerprint = ANY(%s)'
    params = [q['symbol'],q['start_ms'],q['end_ms']]
    if revisions is not None:params.append(revisions)
    params.append(MAX_ROWS+1)
    with conn.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        cur.execute("SET LOCAL lock_timeout = '1000ms'")
        cur.execute("""SELECT CASE WHEN sum(octet_length(record::text)) OVER() <= 8388608
            AND max(octet_length(record::text)) OVER() <= 1048576 THEN record ELSE NULL END
            FROM (SELECT record,start_ms,fingerprint FROM provenance_minutes
            WHERE symbol=%s AND start_ms>=%s AND start_ms<%s""" + revision_sql + """
            ORDER BY start_ms,fingerprint LIMIT %s) bounded ORDER BY start_ms,fingerprint""",
            tuple(params))
        rows=cur.fetchall()
        if any(r[0] is None for r in rows):raise ValueError('BYTE_LIMIT')
        return [r[0] for r in rows]


def read_postgres(conn, request, trust):
    """Compatibility v1 export through the bounded source-owned SQL reader."""
    return export_records(_read_records_postgres(conn,request),request,trust)
