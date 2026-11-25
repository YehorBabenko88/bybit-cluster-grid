"""Causal persisted observations: exact clocks, never source/quote authority.

SourceGrid204897; active canonical v2 only. Math owns quantitative domains.
"""
import copy,hashlib,json,math,re,time
from datetime import datetime,timezone
from market_math import paper_input_numeric_integrity

SYMBOLS=frozenset('BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT AVAXUSDT LINKUSDT DOTUSDT'.split())
FEEDS=frozenset(('ticker','orderbook','open_interest','funding'))
STATUSES=frozenset(('unknown','available','missing','stale','unsupported','degraded'))
MAX_ROWS=1000
MAX_ROW_BYTES=1048576
MAX_BYTES=8388608
DEADLINE=5.0
EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)
PAPER_SCHEMA='market_data.paper-inputs.v2'
PAPER_TAPE=frozenset('start_ms open high low close buy_volume sell_volume buy_count sell_count trade_count delta cvd range aggressor_imbalance'.split())
PAPER_BOOK=frozenset(('best_bid','best_ask','sequence','update_id','cts','_quality'))
PAPER_FUNDING=frozenset(('funding_rate','funding_interval_hour','next_funding_time'))
PAPER_TYPES=frozenset(('trade_tape_250ms','orderbook_snapshot','derivatives_ticker'))
PAPER_ROW_FIELDS=frozenset(('id','symbol','event_type','source','event_us','ingest_us','payload','payload_sha256','row_sha256'))
PAPER_QUALIFIERS=dict(point_in_time_availability='UNKNOWN',availability_basis='CALLER_DECLARED_ROW_CLOCK_CUT_NOT_COMMIT_OR_PIT',source_authenticity='NOT_EVALUATED',source_completeness='NOT_EVALUATED',execution_authority=False,trading_authorized=False,payload_hash_basis='CANONICAL_PERSISTED_JSON_NOT_WIRE_BYTES',sequence_scope='MONOTONIC_PERSISTED_SAMPLES_NOT_CONTIGUOUS_STREAM')

class ExportBlocked(ValueError):
    """Typed unavailability, never proof of corrupt or absent source events."""

def _microseconds(value):
    if type(value) is not str or re.fullmatch('0|[1-9][0-9]{0,17}',value) is None or int(value)>253402300799999999:
        _block('PAPER_CLOCK')
    return int(value)

def _numeric(kind,payload):
    try:valid=paper_input_numeric_integrity(kind,payload)
    except Exception:_block('PAPER_PAYLOAD')
    if valid is not True:_block('PAPER_PAYLOAD')


def _block(code):
    raise ExportBlocked('BLOCKED_'+code) from None


def _closed_map(value,expected,*,subset=False):
    """Bound cardinality before key iteration/hash; never build a set of input."""
    if type(value) is not dict:return False
    if (len(value)>len(expected) if subset else len(value)!=len(expected)):return False
    return all(type(key) is str and len(key)<=64 and key in expected for key in value)


def _request(q):
    keys={'symbol','start_ms','end_ms','as_of_ms','max_age_ms'}
    if not _closed_map(q,keys) or type(q['symbol']) is not str or q['symbol'] not in SYMBOLS:
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
        if not 1<=len(v)<=64:_block("CLOCK")
        try:v=datetime.fromisoformat(v)
        except ValueError:_block('CLOCK')
    if type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None:_block('CLOCK')
    v=v.astimezone(timezone.utc)
    delta=v-EPOCH
    us=(delta.days*86400+delta.seconds)*1000000+delta.microseconds
    return v.isoformat(timespec='microseconds'),us


def _bytes(value,*,limit=MAX_BYTES):
    """Exact ensure_ascii JSON size without serializing an over-budget graph."""
    size=0;nodes=0;stack=[(iter((value,)),False)]
    def charge(count):
        nonlocal size
        size+=count
        if size>limit:_block('BYTE_LIMIT')
    def string_size(text):
        if type(text) is not str:_block('PAYLOAD')
        if len(text)>limit:_block('BYTE_LIMIT')
        charge(2)
        for char in text:
            code=ord(char)
            charge(2 if char in ('"','\\','\b','\f','\n','\r','\t') else
                   1 if 32<=code<=126 else 6 if code<=65535 else 12)
    while stack:
        iterator,mapping=stack[-1]
        try:item=next(iterator)
        except StopIteration:stack.pop();continue
        if mapping:
            key,item=item;string_size(key);charge(1)
        nodes+=1
        if nodes>100000:_block('BYTE_LIMIT')
        if type(item) in (dict,list,tuple):
            if len(stack)>=16:_block('PAYLOAD')
            charge(2+max(0,len(item)-1))
            stack.append((iter(item.items()) if type(item) is dict else iter(item),type(item) is dict))
        elif type(item) is str:string_size(item)
        else:
            if type(item) is int and item.bit_length()>limit*4:_block('BYTE_LIMIT')
            if type(item) not in (int,float,bool,type(None)):_block('PAYLOAD')
            try:charge(len(json.dumps(item,ensure_ascii=True,allow_nan=False,separators=(',',':'))))
            except (TypeError,ValueError,OverflowError):_block('PAYLOAD')
    return size


def _paper_hash(value):
    try:raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    except (TypeError,ValueError,OverflowError,RecursionError):_block('PAPER_PAYLOAD')
    return hashlib.sha256(raw).hexdigest()


def _paper_hex(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None


def _paper_request(request):
    if not _closed_map(request,{'symbol','after_id','start_ms','end_ms','as_of_ms','max_age_ms'}):_block('PAPER_REQUEST')
    if type(request['after_id']) is not int or not 0<=request['after_id']<=2**53-1:_block('PAPER_REQUEST')
    base={k:v for k,v in request.items() if k!='after_id'}
    _request(base);return dict(request)


def _paper_int(value,*,minimum=0):
    if type(value) is str and len(value)<=16 and value.isascii() and value.isdecimal():value=int(value)
    if type(value) is not int or not minimum<=value<=2**53-1:_block('PAPER_PAYLOAD')
    return value


def _paper_payload(kind,payload,q,event_us,ingest_us):
    projected,known=_paper_domain_payload(kind,payload,q,event_us,ingest_us)
    if '_producer_connection' in payload:
        context=payload['_producer_connection']
        if not _closed_map(context,{'schema','venue','category','endpoint','connection_id','scope'}):_block('PAPER_CONNECTION')
        if context['schema']!='market_data.public-market-connection.v1' or context['venue']!='bybit' or context['category']!='linear' or context['endpoint']!='wss://stream.bybit.com/v5/public/linear' or context['scope']!='PRODUCER_DECLARED_LOCAL_CONNECTION_NOT_REMOTE_AUTHENTICATION':_block('PAPER_CONNECTION')
        if type(context['connection_id']) is not str or re.fullmatch('[a-f0-9]{32}',context['connection_id']) is None:_block('PAPER_CONNECTION')
        projected['_producer_connection']=copy.deepcopy(context)
    return projected,known


def _paper_context_status(rows):
    # Book and ticker share one MicrostructureCollector connection. Public tape
    # has its own per-symbol socket: equality across those channels is incorrect.
    channels={};available=bool(rows)
    for row in rows:
        context=row['payload'].get('_producer_connection')
        if context is None:available=False;continue
        channel='tape' if row['event_type']=='trade_tape_250ms' else 'book_and_ticker'
        identity=context['connection_id']
        if channel in channels and channels[channel]!=identity:available=False
        channels[channel]=identity
    return 'CONSISTENT' if available else 'UNAVAILABLE'


def _validate_paper_inputs(packet):
    """Recheck a closed packet's bounds/consistency, never authenticate its author.

    Declared ingest clocks do not prove commit, publication or point-in-time availability. Sequence numbers
    and IDs are sampled/noncontiguous; regressions block but jumps prove no gap.
    Old merged funding fields remain unavailable without their individual clocks.
    """
    started=time.monotonic()
    expected={'schema','request','rows','cursor','funding_status','availability','output_truncated','producer_context_status',*PAPER_QUALIFIERS}
    if not _closed_map(packet,expected) or packet['schema']!=PAPER_SCHEMA:_block('PAPER_PACKET')
    for key,value in PAPER_QUALIFIERS.items():
        if type(packet[key]) is not type(value) or packet[key]!=value:_block('PAPER_PACKET')
    q=_paper_request(packet['request']);rows=packet['rows']
    if type(rows) is not list or len(rows)>MAX_ROWS:_block('ROW_LIMIT')
    if _bytes(packet)>MAX_BYTES:_block('BYTE_LIMIT')
    availability=packet['availability']
    if not _closed_map(availability,{'mode','as_of_ms','cut_before_id','state','scope'}) or availability['mode']!='VISIBLE_ID_PREFIX' or availability['scope']!='SELECTED_VISIBLE_ROWS_NOT_STREAM_COMPLETENESS' or type(availability['as_of_ms']) is not int or availability['as_of_ms']!=q['as_of_ms']:_block('PAPER_AVAILABILITY')
    cut=availability['cut_before_id']
    if cut is not None and (type(cut) is not int or not 0<cut<=2**53-1):_block('PAPER_AVAILABILITY')
    if type(packet['output_truncated']) is not bool or packet['output_truncated']!=(cut is not None):_block('PAPER_AVAILABILITY')
    previous=q['after_id'];last_event={};last_book=None;known=False
    for row in rows:
        if time.monotonic()-started>DEADLINE:_block('DEADLINE')
        if not _closed_map(row,PAPER_ROW_FIELDS) or _bytes(row,limit=MAX_ROW_BYTES)>MAX_ROW_BYTES:_block('PAPER_ROW')
        if type(row['id']) is not int or not previous<row['id']<=2**53-1 or row['symbol']!=q['symbol'] or row['source']!='bybit' or row['event_type'] not in PAPER_TYPES:_block('PAPER_ROW')
        previous=row['id'];event=_microseconds(row['event_us']);ingest=_microseconds(row['ingest_us']);kind=row['event_type']
        if type(event) is not int or type(ingest) is not int or event<0 or ingest<0:_block('PAPER_CLOCK')
        if not q['start_ms']*1000<=event<q['end_ms']*1000 or not 0<=q['as_of_ms']*1000-event<=q['max_age_ms']*1000 or not 0<=q['as_of_ms']*1000-ingest<=q['max_age_ms']*1000 or ingest<event:_block('PAPER_CLOCK')
        if kind in last_event and event<=last_event[kind]:_block('PAPER_SEQUENCE')
        last_event[kind]=event
        if not _paper_hex(row['payload_sha256']) or not _paper_hex(row['row_sha256']) or row['row_sha256']!=_paper_hash({k:v for k,v in row.items()if k!='row_sha256'}):_block('PAPER_HASH')
        projected,funding_known=_paper_payload(kind,row['payload'],q,event,ingest)
        if projected!=row['payload']:_block('PAPER_PAYLOAD')
        if kind=='derivatives_ticker':known=funding_known
        if kind=='orderbook_snapshot':
            current=(projected['sequence'],projected['update_id'])
            if last_book is not None and any(a<=b for a,b in zip(current,last_book)):_block('PAPER_SEQUENCE')
            last_book=current
    context_status=_paper_context_status(rows)
    if packet['producer_context_status']!=context_status:_block('PAPER_CONNECTION')
    known=known and context_status=='CONSISTENT'
    if type(packet['cursor']) is not int or packet['cursor']!=previous or packet['funding_status']!=('KNOWN_SOURCE_FIELDS'if known else'UNAVAILABLE'):_block('PAPER_PACKET')
    if cut is not None and cut<=previous:_block('PAPER_AVAILABILITY')
    expected_state='AVAILABLE' if cut is None else 'PARTIAL' if rows else 'UNAVAILABLE'
    if availability['state']!=expected_state:_block('PAPER_AVAILABILITY')
    result=copy.deepcopy(packet)
    if time.monotonic()-started>DEADLINE:_block('DEADLINE')
    return result


def validate_paper_inputs(packet):
    """Closed packet consistency validation; never source authentication."""
    try:return _validate_paper_inputs(packet)
    except ExportBlocked:raise
    except Exception:_block('PAPER_PACKET')


def export_paper_inputs(records,request):
    """Declared persisted input with a caller-clock cut, never commit/publication/PIT proof.

    A future database ingest ends the prefix before that ID. No later IDs are
    emitted/skipped; the cursor remains the last emitted row. This is a declared
    availability cut, never successful byte/row-budget truncation or a claim of
    commit-order completeness. Future exchange clocks remain rejected.
    """
    q=_paper_request(request);out=[];started=time.monotonic();total=0;raw_total=0;cut=None
    if type(records) not in (list,tuple) or len(records)>MAX_ROWS:_block('ROW_LIMIT')
    # Enforce ALL selected raw payload budgets before any availability prefix.
    for raw in records:
        if time.monotonic()-started>DEADLINE:_block('DEADLINE')
        if type(raw) is not dict or type(raw.get('payload')) is not dict:_block('PAPER_ROW')
        raw_size=_bytes(raw['payload'],limit=MAX_ROW_BYTES);raw_total+=raw_size
        if raw_size>MAX_ROW_BYTES or raw_total>MAX_BYTES:_block('BYTE_LIMIT')
    known=False;previous=q['after_id']
    for raw in records:
        if time.monotonic()-started>DEADLINE:_block('DEADLINE')
        try:
            if type(raw['id']) is not int or not previous<raw['id']<=2**53-1 or raw['symbol']!=q['symbol'] or raw['source']!='bybit' or type(raw['event_type']) is not str or raw['event_type'] not in PAPER_TYPES:_block('PAPER_ROW')
            previous=raw['id']
            _,event=_timestamp(raw['event_ts']);_,ingest=_timestamp(raw['ingest_ts'])
            if not q['start_ms']*1000<=event<q['end_ms']*1000 or not 0<=q['as_of_ms']*1000-event<=q['max_age_ms']*1000 or ingest<event:_block('PAPER_CLOCK')
            if ingest>q['as_of_ms']*1000:
                cut=raw['id'];break
            payload,funding_known=_paper_payload(raw['event_type'],raw['payload'],q,event,ingest)
            row=dict(id=raw['id'],symbol=raw['symbol'],source=raw['source'],event_type=raw['event_type'],event_us=str(event),ingest_us=str(ingest),payload=payload,payload_sha256=_paper_hash(raw['payload']))
            row['row_sha256']=_paper_hash(row);out.append(row);total+=_bytes(row)
            if total>MAX_BYTES:_block('BYTE_LIMIT')
            if raw['event_type']=='derivatives_ticker':known=funding_known
        except ExportBlocked:raise
        except Exception:_block('PAPER_ROW')
    availability=dict(mode='VISIBLE_ID_PREFIX',as_of_ms=q['as_of_ms'],cut_before_id=cut,state='AVAILABLE'if cut is None else'PARTIAL'if out else'UNAVAILABLE',scope='SELECTED_VISIBLE_ROWS_NOT_STREAM_COMPLETENESS')
    context_status=_paper_context_status(out);known=known and context_status=='CONSISTENT'
    packet=dict(schema=PAPER_SCHEMA,request=q,rows=out,cursor=out[-1]['id']if out else q['after_id'],funding_status='KNOWN_SOURCE_FIELDS'if known else'UNAVAILABLE',producer_context_status=context_status,availability=availability,output_truncated=cut is not None,**PAPER_QUALIFIERS)
    result=validate_paper_inputs(packet)
    if time.monotonic()-started>DEADLINE:_block('DEADLINE')
    return result




def paper_funding_at(packet,*,row_id,now_ms):
    """Use-time funding assessment without rewriting source selection metadata.

    The original request/as-of, visibility cut, cursor, rows and hashes stay
    unchanged. Only the latest selected funding row's actual field clocks are
    assessed at the caller's later clock. This grants no source authentication.
    """
    started=time.monotonic();checked=validate_paper_inputs(packet)
    q=checked['request']
    if type(now_ms) is not int or not q['as_of_ms']<=now_ms<=253402300799999:_block('PAPER_CLOCK')
    if type(row_id) is not int or not 0<row_id<=2**53-1:_block('PAPER_FUNDING_ROW')
    rows=[row for row in checked['rows'] if row['event_type']=='derivatives_ticker']
    if not rows or rows[-1]['id']!=row_id:_block('PAPER_FUNDING_ROW')
    row=rows[-1];known=False
    if checked['funding_status']=='KNOWN_SOURCE_FIELDS' and checked['producer_context_status']=='CONSISTENT':
        use_time=dict(q,as_of_ms=now_ms)
        _,known=_paper_payload(row['event_type'],row['payload'],use_time,_microseconds(row['event_us']),_microseconds(row['ingest_us']))
    result=dict(funding_status='KNOWN_SOURCE_FIELDS' if known else 'UNAVAILABLE',evaluated_at_ms=now_ms,
                source_request_sha256=_paper_hash(q),row_sha256=row['row_sha256'])
    if time.monotonic()-started>DEADLINE:_block('DEADLINE')
    return result


def _paper_domain_payload(kind,payload,q,event_us,ingest_us):
    if type(payload) is not dict:_block('PAPER_PAYLOAD')
    if kind=='trade_tape_250ms':
        if not PAPER_TAPE<=payload.keys():_block('PAPER_PAYLOAD')
        out={key:_scalar(payload[key]) for key in sorted(PAPER_TAPE)}
        for key in ('start_ms','buy_count','sell_count','trade_count'):out[key]=_paper_int(out[key])
        if out['start_ms']*1000!=event_us or (out['start_ms']+250)*1000>min(ingest_us,q['as_of_ms']*1000):_block('PAPER_OPEN_BUCKET')
        _numeric(kind,out)
        return out,False
    if kind=='orderbook_snapshot':
        if not {'best_bid','best_ask','sequence','update_id','_quality'}<=payload.keys():_block('PAPER_PAYLOAD')
        out={key:(_quality(payload[key],q['symbol']) if key=='_quality'else _scalar(payload[key])) for key in sorted(PAPER_BOOK & payload.keys())}
        for key in ('sequence','update_id'):out[key]=_paper_int(out[key],minimum=1)
        if out.get('cts') is not None:out['cts']=_paper_int(out['cts'],minimum=1)
        quality=out['_quality']
        if type(quality) is not dict or quality.get('feeds',{}).get('orderbook',{}).get('status')!='available':_block('PAPER_BOOK')
        _numeric(kind,out)
        return out,False
    if kind!='derivatives_ticker':_block('PAPER_KIND')
    if not PAPER_FUNDING & payload.keys():_block('PAPER_PAYLOAD')
    out={key:_scalar(payload[key]) for key in sorted(PAPER_FUNDING & payload.keys())}
    _numeric(kind,out)
    if '_field_observations' not in payload:return out,False
    evidence=payload['_field_observations']
    if not _closed_map(evidence,{'schema','clock_basis','fields'}) or evidence['schema']!='market_data.ticker-field-observations.v1' or evidence['clock_basis']!='EXCHANGE_FRAME_TS_AND_PROCESS_WALL_CLOCK':_block('PAPER_FUNDING_PROOF')
    fields=evidence['fields']
    if not _closed_map(fields,PAPER_FUNDING,subset=True):_block('PAPER_FUNDING_PROOF')
    known=len(fields)==len(PAPER_FUNDING)
    for key,proof in fields.items():
        if key not in out or out[key] is None or not _closed_map(proof,{'event_ms','observed_ms','value_sha256'}):_block('PAPER_FUNDING_PROOF')
        if not _paper_hex(proof['value_sha256']) or proof['value_sha256']!=_paper_hash(out[key]):_block('PAPER_FUNDING_PROOF')
        event=proof['event_ms'];observed=proof['observed_ms']
        if type(event) is not int or type(observed) is not int or not 0<event<=observed<=q['as_of_ms'] or event*1000>event_us:_block('PAPER_CLOCK')
        if q['as_of_ms']-event>q['max_age_ms'] or q['as_of_ms']-observed>q['max_age_ms']:known=False
    out['_field_observations']=copy.deepcopy(evidence)
    return out,known


def assess_paper_funding_rows(packet,*,now_ms):
    """Assess every visible ticker independently, never borrowing the last row.

    Values and field clocks remain producer declarations, not remote authority
    or physical availability. Results are detached and leave packet hashes intact.
    """
    started=time.monotonic();checked=validate_paper_inputs(packet);q=checked['request']
    if type(now_ms) is not int or not q['as_of_ms']<=now_ms<=253402300799999:_block('PAPER_CLOCK')
    use_time=dict(q,as_of_ms=now_ms);request_sha=_paper_hash(q);results=[]
    for row in checked['rows']:
        if row['event_type']!='derivatives_ticker':continue
        projected,known=_paper_payload(row['event_type'],row['payload'],use_time,_microseconds(row['event_us']),_microseconds(row['ingest_us']))
        fields={key:projected[key] for key in sorted(PAPER_FUNDING) if key in projected}
        proofs=projected.get('_field_observations',{}).get('fields',{})
        states={}
        for key in sorted(PAPER_FUNDING):
            if key not in fields:state='OMITTED'
            elif fields[key] is None:state='EXPLICIT_UNKNOWN'
            elif key not in proofs:state='PROOF_MISSING'
            elif now_ms-proofs[key]['event_ms']>q['max_age_ms'] or now_ms-proofs[key]['observed_ms']>q['max_age_ms']:state='STALE'
            else:state='KNOWN_SOURCE_FIELD'
            states[key]=state
        results.append(dict(row_id=row['id'],funding_status='KNOWN_SOURCE_FIELDS' if known and checked['producer_context_status']=='CONSISTENT' else 'UNAVAILABLE',
                            evaluated_at_ms=now_ms,source_request_sha256=request_sha,row_sha256=row['row_sha256'],
                            fields=fields,field_observations=copy.deepcopy(proofs),field_states=states))
        if time.monotonic()-started>DEADLINE:_block('DEADLINE')
    if time.monotonic()-started>DEADLINE:_block('DEADLINE')
    return tuple(results)
