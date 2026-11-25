"""Opt-in pure historical catalog and turnover rollup v1.2.

Catalogs and receipts are independently provisioned declarations. No endpoint,
producer, connection creation, write, authenticity or execution authority.
"""
from decimal import Decimal
import re
from .history_contract import (_snapshot_json, _clock, _units, _number, _version,
    TURNOVER_BASIS, AVAILABILITY_BASIS, FINANCIAL_ENCODING)
from .history_export import _read_records_postgres, MAX_ROWS, MAX_BYTES
from .history_export_v12 import export_records_v12
from .history_export_v11 import _dataset_content
from .history_snapshot import (_candle, TIMEFRAME_MINUTES, MULTIPIN_MINUTES,
    MAX_SEQUENCE_CANDLES, MAX_SEQUENCE_MINUTES, MAX_SEQUENCE_PINS, IDENTITY_FIELDS)
from .provenance import digest

SELECTION_SCHEMA = 'market_data.history.selection.v1.2'
CATALOG_SCHEMA = 'market_data.history.catalog-entry.v1.2'
REQUEST_KEYS = {'schema','venue','market_type','symbol','start_ms','end_ms','as_of_ms','max_age_ms','units'}
TRUST_KEYS = {'schema','identity','source_revision','epoch','receipts','receipt_pins','evidence_class'}
RECEIPT_KEYS = {'schema','record_api_version','dataset_schema','fingerprint','venue','available_at_ms','watermark_ms','complete','units','evidence_class','turnover_basis'}
DECLARATIONS = {'turnover_basis':TURNOVER_BASIS,'availability_basis':AVAILABILITY_BASIS,
    'financial_encoding':FINANCIAL_ENCODING,'source_authentication':'NOT_EVALUATED'}
ROW_KEYS = {'open','high','low','close','volume','turnover','event_start_ms','event_end_ms',
    'available_at_ms','revision','source_event_start_ms','source_event_end_ms','watermark_ms','source_receipt_hash'}

def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('V12_DIGEST')
    return value

def _selection(selection):
    s = _snapshot_json(selection)
    if type(s) is not dict or s.get('schema') != SELECTION_SCHEMA:
        raise ValueError('V12_SELECTION_SCHEMA')
    operation = s.get('operation')
    if operation not in ('minutes','window','multipin','series'):
        raise ValueError('V12_OPERATION')
    multi = operation in ('multipin','series')
    keys = {'schema','operation','venue','market_type','symbol','start_ms','end_ms',
            'snapshot_ids' if multi else 'snapshot_id'}
    if operation != 'minutes': keys.add('timeframe')
    if set(s) != keys: raise ValueError('V12_SELECTION_KEYS')
    if any(type(s[k]) is not str or not s[k] for k in IDENTITY_FIELDS):
        raise ValueError('V12_IDENTITY')
    start,end = _clock(s['start_ms']),_clock(s['end_ms'])
    if start % 60000 or end % 60000 or start >= end:
        raise ValueError('V12_BOUNDS')
    if multi:
        pins=s['snapshot_ids'];limit=MAX_SEQUENCE_PINS if operation=='series' else 8
        if type(pins) is not list or not 1<=len(pins)<=limit:
            raise ValueError('V12_PINS')
        for pin in pins:_hash(pin)
        if len(set(pins))!=len(pins):raise ValueError('V12_PINS')
    else:
        _hash(s['snapshot_id'])
        if end-start>MAX_ROWS*60000:raise ValueError('V12_BOUNDS')
    if operation!='minutes':
        tf=s['timeframe'];allowed=MULTIPIN_MINUTES if multi else TIMEFRAME_MINUTES
        if type(tf) is not str or tf not in allowed:raise ValueError('V12_TIMEFRAME')
        width=allowed[tf]*60000;anchor=4*86400000 if tf=='1w' else 0
        maximum=(min(MAX_SEQUENCE_CANDLES*width,MAX_SEQUENCE_MINUTES*60000)
                 if operation=='series' else width if multi else MAX_ROWS*60000)
        if ((start-anchor)%width or (end-anchor)%width or not width<=end-start<=maximum):
            raise ValueError('V12_ALIGNMENT')
    return s

def _entry(pin,catalog):
    if type(catalog) is not dict:raise ValueError('V12_CATALOG_LITERAL')
    # Admit the complete bounded literal graph before hashing/lookup can invoke
    # a foreign key equality method, including unused colliding catalog keys.
    catalog=_snapshot_json(catalog,max_bytes=MAX_BYTES)
    raw=catalog.get(pin)
    if raw is None:raise ValueError('V12_NOT_PROVISIONED')
    entry=_snapshot_json(raw,max_bytes=MAX_BYTES)
    if (type(entry) is not dict or set(entry)!={'schema','request','trust','revisions','dataset_id','dataset_fingerprint'}
            or entry['schema']!=CATALOG_SCHEMA or digest(entry)!=pin):
        raise ValueError('V12_CATALOG_PIN')
    q,t,revisions=entry['request'],entry['trust'],entry['revisions']
    if type(q) is not dict or set(q)!=REQUEST_KEYS or q['schema']!='market_data.history.request.v1.2':
        raise ValueError('V12_REQUEST')
    if type(t) is not dict or set(t)!=TRUST_KEYS or t['schema']!='market_data.history.trust.v1.2' or t['evidence_class']!='HISTORICAL':
        raise ValueError('V12_TRUST')
    for k in IDENTITY_FIELDS:
        if type(q[k]) is not str or not q[k]:raise ValueError('V12_IDENTITY')
    for k in ('identity','source_revision','epoch'):
        if type(t[k]) is not str or not t[k]:raise ValueError('V12_SOURCE')
    start,end,asof,age=(_clock(q[k]) for k in ('start_ms','end_ms','as_of_ms','max_age_ms'))
    count=(end-start)//60000
    if start%60000 or end%60000 or not 1<=count<=MAX_ROWS or not end<=asof<=end+age:
        raise ValueError('V12_REQUEST_BOUNDS')
    _units(q['units']);_hash(entry['dataset_id']);_hash(entry['dataset_fingerprint'])
    if type(revisions) is not list or len(revisions)!=count:
        raise ValueError('V12_REVISIONS')
    for fp in revisions:_hash(fp)
    if len(set(revisions))!=count:raise ValueError('V12_REVISIONS')
    if (type(t['receipts']) is not dict or type(t['receipt_pins']) is not dict
            or set(t['receipts'])!=set(revisions) or set(t['receipt_pins'])!=set(revisions)):
        raise ValueError('V12_RECEIPT_ROSTER')
    for i,fp in enumerate(revisions):
        a=t['receipts'][fp]
        if (type(a) is not dict or set(a)!=RECEIPT_KEYS or a['schema']!='market_data.history.receipt.v1.2'
                or a['dataset_schema']!='market_data.dataset.v1.2' or a['fingerprint']!=fp
                or a['venue']!=q['venue'] or a['units']!=q['units'] or a['evidence_class']!='HISTORICAL'
                or a['turnover_basis']!=TURNOVER_BASIS or a['complete'] is not True):
            raise ValueError('V12_RECEIPT')
        _version(a['record_api_version'])
        known,watermark=_clock(a['available_at_ms']),_clock(a['watermark_ms'])
        if not start+(i+1)*60000<=watermark<=known<=asof:
            raise ValueError('V12_RECEIPT_CLOCK')
        if _hash(t['receipt_pins'][fp])!=digest(a):raise ValueError('V12_RECEIPT_PIN')
    return entry

def _matching(s,entry):
    if any(type(s[k]) is not type(entry['request'][k]) or s[k]!=entry['request'][k]
           for k in (*IDENTITY_FIELDS,'start_ms','end_ms')):
        raise ValueError('V12_SELECTION_MISMATCH')

def select_snapshot_v12(conn,selection,catalog,*,continuing=False):
    if type(continuing) is not bool:raise ValueError('V12_LITERAL_CONTINUATION_REQUIRED')
    s=_selection(selection)
    if s['operation']!='minutes':raise ValueError('V12_MINUTES_OPERATION')
    entry=_entry(s['snapshot_id'],catalog);_matching(s,entry)
    records=_read_records_postgres(conn,entry['request'],revisions=entry['revisions'],continuing=continuing)
    records=_snapshot_json(records)
    if type(records) is not list or any(type(r) is not dict for r in records) or [r.get('dataset_fingerprint') for r in records]!=entry['revisions']:
        raise ValueError('V12_SNAPSHOT_REVISIONS')
    result=export_records_v12(records,entry['request'],entry['trust'])
    if any(result[k]!=entry[k] for k in ('dataset_id','dataset_fingerprint')):
        raise ValueError('V12_SNAPSHOT_CONTENT')
    return result

def _envelope(envelope):
    x=_snapshot_json(envelope)
    expected={'schema','request','source','evidence_class','rows','source_receipts','execution_authority',
              'trading_authorized','watermark_ms','dataset_id','dataset_fingerprint',*DECLARATIONS}
    if type(x) is not dict or set(x)!=expected or x['schema']!='market_data.history.v1.2':
        raise ValueError('V12_ENVELOPE')
    if (x['evidence_class']!='HISTORICAL' or x['execution_authority'] is not False
            or x['trading_authorized'] is not False or any(x[k]!=v for k,v in DECLARATIONS.items())):
        raise ValueError('V12_DECLARATION')
    q=x['request']
    if type(q) is not dict or set(q)!=REQUEST_KEYS or q['schema']!='market_data.history.request.v1.2':
        raise ValueError('V12_REQUEST')
    _units(q['units'])
    for k in IDENTITY_FIELDS:
        if type(q[k]) is not str or not q[k]:raise ValueError('V12_IDENTITY')
    if type(x['source']) is not dict or set(x['source'])!={'identity','source_revision','epoch'} or any(type(v) is not str or not v for v in x['source'].values()):
        raise ValueError('V12_SOURCE')
    start,end,asof,age=(_clock(q[k]) for k in ('start_ms','end_ms','as_of_ms','max_age_ms'))
    rows=x['rows'];count=(end-start)//60000
    if start%60000 or end%60000 or not 1<=count<=MAX_ROWS or not end<=asof<=end+age or type(rows) is not list or len(rows)!=count:
        raise ValueError('V12_COVERAGE')
    if type(x['source_receipts']) is not list or len(x['source_receipts'])!=count:
        raise ValueError('V12_RECEIPTS')
    if digest({k:v for k,v in x.items() if k!='dataset_fingerprint'})!=_hash(x['dataset_fingerprint']):
        raise ValueError('V12_FINGERPRINT')
    if digest(_dataset_content(x,'market_data.dataset.v1.2'))!=_hash(x['dataset_id']):
        raise ValueError('V12_DATASET_ID')
    from market_math import candle_ohlcv_turnover_valid,executed_notional_consistent
    for i,row in enumerate(rows):
        if type(row) is not dict or set(row)!=ROW_KEYS:raise ValueError('V12_ROW')
        lo=start+i*60000;hi=lo+60000
        for key in ('event_start_ms','event_end_ms','source_event_start_ms','source_event_end_ms','available_at_ms','watermark_ms'):_clock(row[key])
        if (row['event_start_ms']!=lo or row['event_end_ms']!=hi
                or not lo<=row['source_event_start_ms']<=row['source_event_end_ms']<hi
                or not hi<=row['watermark_ms']<=row['available_at_ms']<=asof):
            raise ValueError('V12_ROW_CLOCK')
        _hash(row['revision']);_hash(row['source_receipt_hash'])
        if row['source_receipt_hash']!=x['source_receipts'][i]:raise ValueError('V12_ROW_RECEIPT')
        values=tuple(_number(row[k]) for k in ('open','high','low','close','volume','turnover'))
        if (executed_notional_consistent(values[5],values[4]) is not True or
                candle_ohlcv_turnover_valid(*(Decimal(str(v)) for v in values[:5]),turnover=Decimal(str(values[5]))) is not True):
            raise ValueError('V12_ROW_FINANCIAL_DOMAIN')
    if len({r['revision'] for r in rows})!=count or _clock(x['watermark_ms'])!=max(r['watermark_ms'] for r in rows):
        raise ValueError('V12_ROW_REVISIONS_OR_WATERMARK')
    return x

def _rollup(s,envelopes,parents):
    rows=[row for x in envelopes for row in x['rows']]
    first=envelopes[0];q=first['request']
    for x in envelopes:
        if (x['source']!=first['source'] or x['request']['units']!=q['units'] or x['request']['as_of_ms']!=q['as_of_ms']):
            raise ValueError('V12_PARENT_LINEAGE')
    if len(rows)!=(s['end_ms']-s['start_ms'])//60000 or any(r['event_start_ms']!=s['start_ms']+i*60000 for i,r in enumerate(rows)):
        raise ValueError('V12_PARENT_CONTINUITY')
    minutes=(TIMEFRAME_MINUTES if s['operation']=='window' else MULTIPIN_MINUTES)[s['timeframe']]
    result={'schema':'market_data.history.rollup.v1.2','operation':s['operation'],'selection':s,
            'timeframe':s['timeframe'],'source':first['source'],'units':q['units'],'as_of_ms':q['as_of_ms'],
            'evidence_class':'HISTORICAL',**DECLARATIONS,'parents':parents,
            'execution_authority':False,'trading_authorized':False,
            'rows':[_candle(rows[i:i+minutes],version='v1.2') for i in range(0,len(rows),minutes)]}
    return dict(result,dataset_fingerprint=digest(result))

def rollup_snapshot_v12(envelope,selection,catalog):
    s=_selection(selection)
    if s['operation']!='window':raise ValueError('V12_WINDOW_OPERATION')
    entry=_entry(s['snapshot_id'],catalog);_matching(s,entry)
    x=_envelope(envelope)
    _matching(s,{'request':x['request']})
    if any(x[k]!=entry[k] for k in ('dataset_id','dataset_fingerprint')):
        raise ValueError('V12_PARENT_PIN')
    return _rollup(s,[x],[{'snapshot_id':s['snapshot_id'],'dataset_id':x['dataset_id'],
                           'dataset_fingerprint':x['dataset_fingerprint']}])

def plan_multipin_v12(selection,catalog):
    s=_selection(selection)
    if s['operation'] not in ('multipin','series'):raise ValueError('V12_MULTIPIN_OPERATION')
    pages=[];cursor=s['start_ms'];common=None
    for pin in s['snapshot_ids']:
        entry=_entry(pin,catalog);q,t=entry['request'],entry['trust']
        if any(q[k]!=s[k] for k in IDENTITY_FIELDS) or q['start_ms']!=cursor or q['end_ms']>s['end_ms']:
            raise ValueError('V12_PAGE_CONTINUITY')
        lineage=(q['as_of_ms'],q['units'],*(t[k] for k in ('identity','source_revision','epoch')))
        if common is not None and lineage!=common:raise ValueError('V12_PAGE_LINEAGE')
        common=lineage;cursor=q['end_ms']
        pages.append({'schema':SELECTION_SCHEMA,'operation':'minutes','snapshot_id':pin,
                      **{k:q[k] for k in (*IDENTITY_FIELDS,'start_ms','end_ms')}})
    if cursor!=s['end_ms']:raise ValueError('V12_PAGE_CONTINUITY')
    return pages

def read_multipin_rollup_v12(conn,selection,pages,catalog):
    s=_selection(selection);planned=plan_multipin_v12(s,catalog)
    if _snapshot_json(pages)!=planned:raise ValueError('V12_PAGE_PLAN')
    # Freeze every selected entry before the first source read/callback.
    frozen={p['snapshot_id']:_entry(p['snapshot_id'],catalog) for p in planned}
    envelopes=[];parents=[]
    for page in planned:
        x=select_snapshot_v12(conn,page,frozen,continuing=bool(parents));x=_envelope(x)
        envelopes.append(x);parents.append({'snapshot_id':page['snapshot_id'],
            'dataset_id':x['dataset_id'],'dataset_fingerprint':x['dataset_fingerprint']})
    return _rollup(s,envelopes,parents)
