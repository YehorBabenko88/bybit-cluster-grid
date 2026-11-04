"""Bounded laboratory observations, never quote admission or source authentication.

Caller supplies a fresh psycopg connection; this module owns only its read-only
transaction, never the connection. No connection strings, SQL, or paths accepted.
Range is half-open in exchange event_ts. ingest_ts is the persisted database clock,
not receiver receipt time or proof of availability. as_of_ms is caller-declared,
not a live clock assertion; observation_status describes event age only. Merged
ticker deltas do not prove freshness of ANY individual last/bid/ask field.

Source completeness is NOT_EVALUATED, including when no rows are selected.
Output order is (event_ts,id). No pagination/truncation: any budget breach BLOCKS
all output. Missing payload keys remain absent; explicit null remains null.
Scalar projection intentionally excludes book/walls and unrecognized payload keys.
SQL integration is separate from synthetic unit tests.
"""
import json
import math
import re
import time
from datetime import datetime, timezone

SYMBOLS=frozenset('BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT AVAXUSDT LINKUSDT DOTUSDT'.split())
TICKER=frozenset('open_interest open_interest_value funding_rate funding_interval_hour next_funding_time mark_price index_price last_price basis_rate bid1_price bid1_size ask1_price ask1_size volume24h turnover24h'.split())
BOOK=frozenset('best_bid best_ask spread bid_depth ask_depth imbalance sequence update_id cts book_update_rate book_add_rate book_cancel_rate book_consume_rate depth_change_rate'.split())
TYPES={'derivatives_ticker':TICKER,'orderbook_snapshot':BOOK}
FEEDS=frozenset(('ticker','orderbook','open_interest','funding'))
STATUSES=frozenset(('unknown','available','missing','stale','unsupported','degraded'))
MAX_ROWS=1000
MAX_ROW_BYTES=1048576
MAX_BYTES=8388608
DEADLINE=5.0
EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)


class ExportBlocked(ValueError):
    """Typed unavailable export, never evidence of corrupt/missing source events."""


def _block(code):
    raise ExportBlocked('BLOCKED_'+code) from None


def _request(q):
    keys={'symbol','start_ms','end_ms','as_of_ms','max_age_ms'}
    if type(q) is not dict or set(q)!=keys or type(q['symbol']) is not str or q['symbol'] not in SYMBOLS:
        _block('REQUEST')
    if any(type(q[k]) is not int or not 0<=q[k]<=253402300799999 for k in keys-{'symbol'}):
        _block('REQUEST')
    if not 0<q['end_ms']-q['start_ms']<=3600000 or not 0<q['max_age_ms']<=3600000:
        _block('REQUEST')
    return dict(q)


def _scalar(v):
    if v is None:return v
    if type(v) is int and abs(v)<=10**30:return v
    if type(v) is float and math.isfinite(v):return v
    # Numeric exchange strings only: arbitrary text must never escape as prices.
    if type(v) is str and len(v)<=128 and re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',v):return v
    _block('PAYLOAD')


def _quality(q,symbol):
    if q is None:return None
    if type(q) is not dict:_block('QUALITY')
    out={}
    if 'symbol' in q:
        if q['symbol']!=symbol:_block('QUALITY')
        out['symbol']=q['symbol']
    for group in ('feeds','missing_counts','last_update'):
        if group not in q:continue
        if type(q[group]) is not dict:_block('QUALITY')
        out[group]={}
        for feed in sorted(FEEDS & q[group].keys()):
            value=q[group][feed]
            if group=='feeds':
                if type(value) is not dict or type(value.get('status')) is not str or value['status'] not in STATUSES:_block('QUALITY')
                # Reasons are free text and intentionally omitted from safe export.
                out[group][feed]={'status':value['status']}
            else:
                if type(value) not in (int,float) or not math.isfinite(value) or value<0:_block('QUALITY')
                if group=='missing_counts' and type(value) is not int:_block('QUALITY')
                out[group][feed]=value
    return out


def _timestamp(v):
    if type(v) is str:
        try:v=datetime.fromisoformat(v)
        except ValueError:_block('CLOCK')
    if type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None:_block('CLOCK')
    v=v.astimezone(timezone.utc)
    delta=v-EPOCH
    us=(delta.days*86400+delta.seconds)*1000000+delta.microseconds
    return v.isoformat(timespec='microseconds'),us


def _bytes(value):
    # Bound traversal before JSON encoding: Python recursion limits vary by host.
    # Iterators keep the traversal stack bounded even for a very wide container.
    stack=[iter((value,))];nodes=0
    while stack:
        try:item=next(stack[-1])
        except StopIteration:
            stack.pop();continue
        nodes+=1
        if nodes>100000:_block('BYTE_LIMIT')
        if type(item) in (dict,list,tuple):
            if len(stack)>=16:_block('PAYLOAD')
            stack.append(iter(item.values() if type(item) is dict else item))
    try:return len(json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode())
    except (TypeError,ValueError,OverflowError,RecursionError):_block('PAYLOAD')


def export_records(records,request):
    """Pure bounded transform of persisted rows; does not grant provenance trust."""
    started=time.monotonic()
    q=_request(request)
    if type(records) not in (list,tuple) or len(records)>MAX_ROWS:_block('ROW_LIMIT')
    out=[];previous=None;total=0
    for raw in records:
        if time.monotonic()-started>DEADLINE:_block('DEADLINE')
        if type(raw) is not dict:_block('ROW')
        try:
            if _bytes(raw if not any(isinstance(v,datetime) for v in raw.values()) else
                      {k:(v.isoformat() if isinstance(v,datetime) else v) for k,v in raw.items()})>MAX_ROW_BYTES:_block('BYTE_LIMIT')
            if type(raw['id']) is not int or raw['id']<=0 or raw['symbol']!=q['symbol'] or raw['event_type'] not in TYPES or raw['source']!='bybit':_block('ROW')
            event_ts,event_us=_timestamp(raw['event_ts']);ingest_ts,_=_timestamp(raw['ingest_ts'])
            key=(event_us,raw['id'])
            if not q['start_ms']*1000<=event_us<q['end_ms']*1000 or previous is not None and key<=previous:_block('ORDER_OR_RANGE')
            previous=key
            payload=raw['payload']
            if type(payload) is not dict:_block('PAYLOAD')
            projected={k:_scalar(payload[k]) for k in sorted(TYPES[raw['event_type']] & payload.keys())}
            if '_quality' in payload:projected['_quality']=_quality(payload['_quality'],q['symbol'])
            age_us=q['as_of_ms']*1000-event_us
            out.append(dict(id=raw['id'],symbol=raw['symbol'],event_type=raw['event_type'],source=raw['source'],
                event_ts=event_ts,ingest_ts=ingest_ts,payload=projected,event_age_ms=age_us/1000,
                observation_status='future' if age_us<0 else 'stale' if age_us>q['max_age_ms']*1000 else 'observed',
                field_freshness='unknown'))
            total+=_bytes(out[-1])
            if total>MAX_BYTES:_block('BYTE_LIMIT')
        except ExportBlocked:raise
        except (KeyError,TypeError,ValueError,OverflowError,RecursionError):_block('ROW')
    result=dict(schema='grid.lab_observations.v1',request=q,evidence_class='persisted_observation_unverified',
                execution_authority=False,trading_authorized=False,rows=out,row_count=len(out),
                output_truncated=False,source_completeness='NOT_EVALUATED',
                selection_scope={'symbol':q['symbol'],'event_types':sorted(TYPES),
                    'start_ms':q['start_ms'],'end_ms':q['end_ms'],
                    'range':'start_ms <= event_ts < end_ms','ordering':['event_ts','id']})
    if _bytes(result)>MAX_BYTES:_block('BYTE_LIMIT')
    return result


# Fixed SQL; external inputs occur only in bind parameters. LIMIT sentinel blocks
# rather than silently returning partial observations. CASE prevents client-side
# materialization of over-budget JSON. Raw payload bytes are guarded too.
_SQL="""SELECT CASE WHEN sum(raw_bytes) OVER()<=8388608
 AND max(raw_bytes) OVER()<=1048576
 AND sum(octet_length(record::text)) OVER()<=8388608
 AND max(octet_length(record::text)) OVER()<=1048576 THEN record ELSE NULL END
 FROM (SELECT event_ts,id,octet_length(payload::text) AS raw_bytes,
 jsonb_build_object('id',id,'symbol',symbol,'source',source,'event_type',event_type,
 'event_ts',event_ts,'ingest_ts',ingest_ts,'payload',
 (SELECT COALESCE(jsonb_object_agg(key,value ORDER BY key),'{}'::jsonb) FROM jsonb_each(payload)
 WHERE key=ANY(%s))) AS record
 FROM market_events WHERE symbol=%s AND event_ts>=to_timestamp(%s/1000.0)
 AND event_ts<to_timestamp(%s/1000.0) AND event_type=ANY(%s)
 ORDER BY event_ts,id LIMIT %s) bounded ORDER BY event_ts,id"""


def read_postgres(conn,request):
    """Fresh caller-owned psycopg connection; never close it or active user work."""
    q=_request(request)
    if getattr(getattr(conn,'info',None),'transaction_status',None)!=0:_block('ACTIVE_TRANSACTION')
    started=time.monotonic()
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                cur.execute("SET LOCAL statement_timeout = '3000ms'")
                cur.execute("SET LOCAL lock_timeout = '1000ms'")
                cur.execute(_SQL,(sorted(TICKER|BOOK|{'_quality'}),q['symbol'],q['start_ms'],q['end_ms'],sorted(TYPES),MAX_ROWS+1))
                rows=cur.fetchall()
                if len(rows)>MAX_ROWS:_block('ROW_LIMIT')
                if any(r[0] is None for r in rows):_block('BYTE_LIMIT')
                if time.monotonic()-started>DEADLINE:_block('DEADLINE')
                return export_records([r[0] for r in rows],q)
    except ExportBlocked:raise
    except Exception:raise ExportBlocked('BLOCKED_SOURCE_READ') from None
