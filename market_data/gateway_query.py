"""Pure canonical synthetic OHLCV preparation; no IO or disclosure authority.

Local profile only. Neither canonical claims nor their digests prove an admitted
dataset, registry, publication, capability, coverage or historical knowledge.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from decimal import Decimal
from market_math import query_minute_grid_ms, candle_ohlcv_turnover_valid

REQUEST_SCHEMA = 'market_data.gateway.ohlcv-query.v1-review2'
MAX_BYTES = 32768
MAX_ROWS = 1440
MAX_U63 = 9223372036854775807
MAX_UTC_MS = 253402300799999
_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
_HASH = r'[0-9a-f]{64}'


class QueryFormatError(ValueError):
    """Invalid or unsupported local preparation profile; no read was attempted."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


# This is a local synthetic row-layout descriptor, not a financial wire adoption.
_DATA_SCHEMA_BYTES = _canonical({
    'schema': 'market_data.gateway.synthetic-ohlcv-row.v1-review1',
    'columns': ['open_time_ms', 'open', 'high', 'low', 'close', 'volume', 'turnover'],
    'source_class': 'SYNTHETIC', 'category': 'linear', 'interval_ms': '60000',
    'financial_encoding': 'canonical-exact-decimal-strings',
    'price_unit': 'quote-per-base', 'volume_unit': 'base', 'turnover_unit': 'quote',
})
DATA_SCHEMA_SHA256 = hashlib.sha256(_DATA_SCHEMA_BYTES).hexdigest()
_PROFILE_BYTES = _canonical({
    'schema': 'market_data.gateway.synthetic-ohlcv-preparation.v1-review2',
    'request_schema': REQUEST_SCHEMA, 'data_schema_sha256': DATA_SCHEMA_SHA256,
    'source_class': 'SYNTHETIC', 'exchange': 'bybit', 'category': 'linear',
    'symbol': 'BTCUSDT', 'interval_ms': '60000', 'max_rows': '1440',
    'range': 'half-open-utc-unix-ms', 'event_cut': 'inclusive-final-candle-end-ms',
    'knowledge_cut': 'exact-retained-manifest-hash-and-revision-claim',
    'dataset_revision': 'separate-local-synthetic-immutable-version-claim',
    'consumer_and_view': 'canonical-uuid4',
    'execution': 'NOT_EXECUTED', 'admission': 'NONE',
})
QUERY_PROFILE_SHA256 = hashlib.sha256(_PROFILE_BYTES).hexdigest()


def data_schema_bytes():
    return _DATA_SCHEMA_BYTES


def query_profile_bytes():
    return _PROFILE_BYTES


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QueryFormatError('duplicate key')
        result[key] = value
    return result


def _no_number(_):
    raise QueryFormatError('numeric literals forbidden')


def _closed(value, keys):
    if type(value) is not dict or len(value) != len(keys) or any(type(key) is not str or len(key)>128 for key in value) or set(value) != set(keys):
        raise QueryFormatError('closed object fields')


def _string(value, pattern):
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        raise QueryFormatError('string grammar')


def _u63(value, *, positive=False):
    _string(value, r'0|[1-9][0-9]{0,18}')
    number = int(value)
    if number > MAX_U63 or (positive and number == 0):
        raise QueryFormatError('u63 range')
    return number


def _preparse_json(raw,*,profile='fixture'):
    """Bound canonical domain container widths before allocating parsed objects.

    This lexical budget does not replace JSON decoding, closed-field validation,
    canonical byte equality, Math qualification or any Root manifest codec.
    """
    stack=[];containers=0;quoted=False;escaped=False;key_start=None;key_escaped=False
    def width(kind,path):
        if profile=='request':
            if kind==91:return 0
            return {():13,('instrument_id',):4,('range',):2,('knowledge_cut',):2,('consumer_context',):3}.get(path,16)
        if kind==123:return 16
        return {('rows',):MAX_ROWS,('rows','*'):7,('cells',):MAX_ROWS,('segments',):1,('objects',):4}.get(path,MAX_ROWS)
    for offset,char in enumerate(raw):
        if quoted:
            if key_start is not None and offset-key_start>128:raise QueryFormatError('object key byte bound')
            if escaped:escaped=False
            elif char==92:escaped=True;key_escaped=True
            elif char==34:
                quoted=False
                if key_start is not None:
                    if key_escaped:raise QueryFormatError('escaped object keys are noncanonical')
                    try:stack[-1]['key']=raw[key_start:offset].decode('ascii')
                    except UnicodeError as exc:raise QueryFormatError('object key grammar') from exc
                    stack[-1]['expect_key']=False;key_start=None
            continue
        if char==34:
            quoted=True;escaped=False;key_escaped=False;key_start=None
            if stack:
                frame=stack[-1];frame['content']=True
                if frame['kind']==123 and frame['expect_key']:key_start=offset+1
        elif char in (123,91):
            path=()
            if stack:
                parent=stack[-1];parent['content']=True
                path=parent['path']+((parent['key'] if parent['kind']==123 else '*'),)
            containers+=1
            if len(stack)>=8 or containers>1456:raise QueryFormatError('JSON depth/container budget')
            cap=width(char,path)
            if cap==0:raise QueryFormatError('array not allowed in request')
            stack.append({'kind':char,'path':path,'commas':0,'content':False,'key':None,'expect_key':char==123,'cap':cap})
        elif char in (125,93):
            if not stack or stack[-1]['kind']!={125:123,93:91}[char]:raise QueryFormatError('JSON nesting')
            stack.pop()
        elif char==44:
            if not stack:raise QueryFormatError('JSON delimiter')
            frame=stack[-1];frame['commas']+=1
            if frame['commas']>=frame['cap']:raise QueryFormatError('JSON field/array cardinality')
            if frame['kind']==123:frame['expect_key']=True;frame['key']=None
        elif char not in (9,10,13,32):
            if stack:stack[-1]['content']=True
    if quoted or stack:raise QueryFormatError('JSON nesting/string')


def _validate(raw):
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        raise QueryFormatError('bounded bytes required')
    # Bound containers before invoking the recursive JSON parser. This closed
    # profile has exactly five objects, no arrays and no container chars in IDs.
    if raw.count(b'{') != 5 or raw.count(b'}') != 5 or b'[' in raw or b']' in raw:
        raise QueryFormatError('container shape')
    _preparse_json(raw,profile='request')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs,
                           parse_int=_no_number, parse_float=_no_number,
                           parse_constant=_no_number)
        _closed(value, ('schema', 'request_id', 'dataset_id', 'dataset_revision', 'source_class',
                        'instrument_id', 'interval_ms', 'data_schema_sha256',
                        'query_profile_sha256', 'range', 'event_cut_ms',
                        'knowledge_cut', 'consumer_context'))
        if (value['schema'] != REQUEST_SCHEMA or value['source_class'] != 'SYNTHETIC'
                or value['data_schema_sha256'] != DATA_SCHEMA_SHA256
                or value['query_profile_sha256'] != QUERY_PROFILE_SHA256
                or value['interval_ms'] != '60000'):
            raise QueryFormatError('unsupported local profile')
        for key in ('request_id', 'dataset_id'):
            _string(value[key], _UUID)
        _u63(value['dataset_revision'], positive=True)
        instrument = value['instrument_id']
        _closed(instrument, ('exchange', 'category', 'symbol', 'instrument_version'))
        if (instrument['exchange'] != 'bybit' or instrument['category'] != 'linear'
                or instrument['symbol'] != 'BTCUSDT'):
            raise QueryFormatError('unsupported synthetic instrument')
        _u63(instrument['instrument_version'], positive=True)
        requested_range = value['range']
        _closed(requested_range, ('start_ms', 'end_ms'))
        start = _u63(requested_range['start_ms'])
        end = _u63(requested_range['end_ms'])
        cutoff = _u63(value['event_cut_ms'])
        try:
            query_minute_grid_ms(start,end,event_cut_ms=cutoff)
        except ValueError as exc:
            raise QueryFormatError('range, cutoff or row bound') from exc
        knowledge = value['knowledge_cut']
        _closed(knowledge, ('manifest_sha256', 'manifest_revision'))
        _string(knowledge['manifest_sha256'], _HASH)
        _u63(knowledge['manifest_revision'], positive=True)
        context = value['consumer_context']
        _closed(context, ('consumer_id', 'view_id', 'authorization_contract_sha256'))
        for key in ('consumer_id', 'view_id'):
            _string(context[key], _UUID)
        _string(context['authorization_contract_sha256'], _HASH)
        if _canonical(value) != raw:
            raise QueryFormatError('noncanonical bytes')
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, KeyError) as exc:
        raise QueryFormatError('invalid request encoding/shape') from exc


@dataclass(frozen=True, slots=True)
class PreparedQuery:
    """Immutable local claim, never an executable capability or store snapshot."""
    canonical_bytes: bytes

    def __post_init__(self):
        _validate(self.canonical_bytes)

    @property
    def request_sha256(self):
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def as_dict(self):
        return _validate(self.canonical_bytes)

    def not_executed(self):
        # Revalidate even locally forged/replaced dataclass payloads. No positive
        # branch or store/callback argument exists before actual ABI admission.
        value = self.as_dict()
        return {
            'schema': 'market_data.gateway.ohlcv-not-executed.v1-review2',
            'status': 'NOT_EXECUTED', 'reason_code': 'DISCLOSURE_ADAPTER_NOT_ADMITTED',
            'request_sha256': self.request_sha256,
            'dataset_id': value['dataset_id'], 'instrument_id': value['instrument_id'],
            'requested_dataset_revision': value['dataset_revision'],
            'data_schema_sha256': DATA_SCHEMA_SHA256,
            'query_profile_sha256': QUERY_PROFILE_SHA256,
            'requested_range': value['range'], 'event_cut_ms': value['event_cut_ms'],
            'requested_knowledge_cut': value['knowledge_cut'],
            'consumer_context': value['consumer_context'],
            'source_class': None, 'native_authenticated': False,
            'rows': None, 'coverage': None, 'gaps': None, 'capabilities': None,
            'resolved_manifest': None,
        }


def prepare_query(request_bytes):
    """Prepare a bounded request claim; never read or execute it."""
    return PreparedQuery(request_bytes)


def _fixture_json(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise QueryFormatError('fixture byte bound')
    _preparse_json(raw)
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs,
                           parse_int=_no_number, parse_float=_no_number,
                           parse_constant=_no_number)
        if _canonical(value) != raw: raise QueryFormatError('fixture canonical bytes')
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise QueryFormatError('fixture encoding') from exc


def _context(value):
    keys=('manifest_sha256','manifest_revision','dataset_id','instrument_id','lineage_sha256','data_schema_sha256','segments_root_sha256','coverage_root_sha256','dependencies_root_sha256','source_class')
    _closed(value,keys)
    value=dict(value)
    for key in ('manifest_sha256','lineage_sha256','data_schema_sha256','segments_root_sha256','coverage_root_sha256','dependencies_root_sha256'):_string(value[key],_HASH)
    _u63(value['manifest_revision'],positive=True);_string(value['dataset_id'],_UUID)
    instrument=value['instrument_id'];_closed(instrument,('exchange','category','symbol','instrument_version'))
    instrument=dict(instrument);value['instrument_id']=instrument
    for key in ('exchange','category','symbol'):_string(instrument[key],r'[A-Za-z0-9]{1,30}')
    _string(value['source_class'],r'[A-Z]{1,16}')
    if (value['source_class']!='SYNTHETIC' or instrument['exchange']!='bybit' or instrument['category']!='linear' or instrument['symbol']!='BTCUSDT' or value['data_schema_sha256']!=DATA_SCHEMA_SHA256):
        raise QueryFormatError('unsupported domain context')
    _u63(instrument['instrument_version'],positive=True)
    return {**value,'instrument_id':dict(instrument)}


def _decode_query_fixture_body(context, manifest_bytes, objects):
    if type(objects) is not dict or len(objects) != 5:
        raise QueryFormatError('exact five-object closure required')
    objects=dict(objects)
    if type(manifest_bytes) is not bytes or not 0 < len(manifest_bytes) <= 16384:
        raise QueryFormatError('manifest byte bound')
    total = len(manifest_bytes)
    for key, raw in objects.items():
        _string(key, _HASH)
        if type(raw) is not bytes or not 0 < len(raw) <= 524288:
            raise QueryFormatError('fixture object byte bound')
        total += len(raw)
    if total > 1048576: raise QueryFormatError('fixture total byte bound')
    for key, raw in objects.items():
        if hashlib.sha256(raw).hexdigest() != key:
            raise QueryFormatError('fixture object hash')
    root = _context(context)
    if hashlib.sha256(manifest_bytes).hexdigest()!=root['manifest_sha256']:
        raise QueryFormatError('manifest hash/context differs')
    lineage_sha=root['lineage_sha256']
    for key in ('segments_root_sha256', 'coverage_root_sha256', 'dependencies_root_sha256', 'data_schema_sha256'):
        _string(root[key], _HASH)
    if root['data_schema_sha256'] != DATA_SCHEMA_SHA256 or objects[DATA_SCHEMA_SHA256] != _DATA_SCHEMA_BYTES:
        raise QueryFormatError('row descriptor profile')

    def record(hash_key, limit, schema, extras):
        value = _fixture_json(objects[root[hash_key]], limit)
        _closed(value, ('schema','source_class','lineage_sha256',*extras))
        if (value['schema'] != schema or value['source_class'] != 'SYNTHETIC'
                or value['lineage_sha256'] != lineage_sha):
            raise QueryFormatError('synthetic record lineage/schema')
        return value

    reference,index,grid=_decode_query_segment_index(objects[root['segments_root_sha256']],context=root)
    start,end=grid[0][0],grid[-1][1]
    allowed_times={lower for lower,_ in grid}
    ref=index['segments'][0]
    rows_raw=objects[reference.sha256]
    if reference.bytes!=len(rows_raw):raise QueryFormatError('segment byte count')
    segment = _fixture_json(rows_raw, 524288)
    _closed(segment, ('schema','source_class','lineage_sha256','data_schema_sha256','interval_ms','rows'))
    if (segment['schema'] != 'market_data.gateway.synthetic-row-segment.v1-review1'
            or segment['source_class'] != 'SYNTHETIC' or segment['lineage_sha256'] != lineage_sha
            or segment['data_schema_sha256'] != DATA_SCHEMA_SHA256 or segment['interval_ms'] != '60000'):
        raise QueryFormatError('segment profile')
    rows = segment['rows']
    if type(rows) is not list or len(rows) > MAX_ROWS or _u63(ref['row_count']) != len(rows):
        raise QueryFormatError('segment row count')
    times = []
    for row in rows:
        if type(row) is not list or len(row) != 7: raise QueryFormatError('row columns')
        time = _u63(row[0])
        if time not in allowed_times or (times and time <= times[-1]):
            raise QueryFormatError('row ordering/range')
        times.append(time)
        values = []
        for text in row[1:]:
            if type(text) is not str or len(text) > 80: raise QueryFormatError('decimal bound')
            _string(text, r'(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?')
            values.append(Decimal(text))
        op,hi,lo,cl,volume,turnover = values
        if not candle_ohlcv_turnover_valid(op,hi,lo,cl,volume,turnover=turnover):
            raise QueryFormatError('OHLCV relation')
    coverage = record('coverage_root_sha256', 524288, 'market_data.gateway.synthetic-coverage.v1-review1',
                      ('data_schema_sha256','segments_root_sha256','interval_ms','declared_range','cells'))
    if (coverage['data_schema_sha256'] != DATA_SCHEMA_SHA256 or coverage['interval_ms'] != '60000'
            or coverage['segments_root_sha256'] != root['segments_root_sha256']
            or coverage['declared_range'] != index['declared_range']):
        raise QueryFormatError('coverage profile/joins')
    cells = coverage['cells']
    if type(cells) is not list or len(cells) != len(grid) or len(cells) > MAX_ROWS:
        raise QueryFormatError('coverage cells')
    actual_present = []
    rules = {'PRESENT':('FIXTURE_GENERATED','NOT_APPLICABLE'),
             'GAP':('FIXTURE_OMISSION','UNKNOWN'), 'UNOBSERVED':('FIXTURE_UNOBSERVED','UNKNOWN')}
    for i, cell in enumerate(cells):
        _closed(cell, ('start_ms','end_ms','disposition','reason','recoverability'))
        expected, expected_end = grid[i]
        if _u63(cell['start_ms']) != expected or _u63(cell['end_ms']) != expected_end:
            raise QueryFormatError('coverage cell ordering')
        disposition = cell['disposition']
        if type(disposition) is not str or disposition not in rules or (cell['reason'],cell['recoverability']) != rules[disposition]:
            raise QueryFormatError('coverage disposition')
        if disposition == 'PRESENT': actual_present.append(expected)
    if times != actual_present: raise QueryFormatError('explicit coverage does not match actual rows')
    dependencies = record('dependencies_root_sha256', 16384, 'market_data.gateway.synthetic-dependencies.v1-review1', ('objects',))
    roles = [('data_schema',DATA_SCHEMA_SHA256),('rows',ref['sha256']),
             ('segment_index',root['segments_root_sha256']),('coverage',root['coverage_root_sha256'])]
    expected_deps = [{'role':role,'sha256':key,'bytes':str(len(objects[key]))} for role,key in roles]
    if dependencies['objects'] != expected_deps or set(objects) != {key for _,key in roles}|{root['dependencies_root_sha256']}:
        raise QueryFormatError('exact dependency closure')
    return {'classification':'SYNTHETIC_FIXTURE_LOCALLY_CHECKED_ONLY',
            'provider_coverage':'UNKNOWN','provider_gaps':'UNKNOWN',
            'publication':'UNPROVEN','registry':'UNPROVEN','execution_authority':False,
            'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
            'manifest_revision':root['manifest_revision'],'dataset_id':root['dataset_id'],
            'instrument_id':root['instrument_id'],'lineage_sha256':lineage_sha,
            'data_schema_sha256':DATA_SCHEMA_SHA256,'declared_range':index['declared_range'],
            'rows':rows,'cells':cells}



def _decode_query_fixture(context,manifest_bytes,objects_by_sha256):
    """Pure local byte/domain consistency, never an authority or Root codec."""
    try:return _decode_query_fixture_body(context,manifest_bytes,objects_by_sha256)
    except (KeyError,TypeError,IndexError,RecursionError) as exc:
        raise QueryFormatError('domain object shape/join') from exc


@dataclass(frozen=True,slots=True)
class QuerySegmentReference:
    sha256:str
    bytes:int
    row_count:int
    def __post_init__(self):
        _string(self.sha256,_HASH)
        if type(self.bytes) is not int or not 1<=self.bytes<=524288 or type(self.row_count) is not int or not 0<=self.row_count<=MAX_ROWS:
            raise QueryFormatError('bounded immutable segment reference required')


def _decode_query_segment_index(index_bytes,*,context):
    """Pure domain reference selection; never reads or authorizes an object."""
    if type(index_bytes) is not bytes or not 0<len(index_bytes)<=16384:
        raise QueryFormatError('segment index byte bound')
    root=_context(context)
    if hashlib.sha256(index_bytes).hexdigest()!=root['segments_root_sha256']:
        raise QueryFormatError('segment index hash/context differs')
    value=_fixture_json(index_bytes,16384)
    _closed(value,('schema','source_class','lineage_sha256','data_schema_sha256','interval_ms','declared_range','segments'))
    if (value['schema']!='market_data.gateway.synthetic-segment-index.v1-review1' or value['source_class']!='SYNTHETIC'
            or value['lineage_sha256']!=root['lineage_sha256'] or value['data_schema_sha256']!=DATA_SCHEMA_SHA256 or value['interval_ms']!='60000'):
        raise QueryFormatError('segment index domain profile')
    _closed(value['declared_range'],('start_ms','end_ms'))
    start,end=(_u63(value['declared_range'][k]) for k in ('start_ms','end_ms'))
    try:grid=query_minute_grid_ms(start,end)
    except ValueError as exc:raise QueryFormatError('segment index range') from exc
    refs=value['segments']
    if type(refs) is not list or len(refs)!=1:raise QueryFormatError('one bounded segment required')
    ref=refs[0];_closed(ref,('sha256','bytes','row_count'))
    result=QuerySegmentReference(ref['sha256'],_u63(ref['bytes'],positive=True),_u63(ref['row_count']))
    if result.row_count>len(grid):raise QueryFormatError('segment count exceeds declared grid')
    return result,value,grid


def decode_query_segment_index(index_bytes,*,context):
    """Return the same canonical bounded index algorithm used by projection."""
    try:return _decode_query_segment_index(index_bytes,context=context)[0]
    except (KeyError,TypeError,IndexError,RecursionError) as exc:
        raise QueryFormatError('segment index shape/join') from exc


def project_query(prepared,*,context,manifest_bytes,objects_by_sha256):
    """Project caller-supplied bytes only; Root must guard every IO/disclosure.

    A forged context never authenticates a source or grants a capability here.
    Generic Root manifest bytes are hash-checked, not parsed by this module.
    """
    if type(prepared) is not PreparedQuery:raise QueryFormatError('exact prepared query required')
    request=prepared.as_dict();root=_context(context)
    if (request['dataset_id']!=root['dataset_id'] or request['instrument_id']!=root['instrument_id']
            or request['knowledge_cut']['manifest_sha256']!=root['manifest_sha256']
            or request['knowledge_cut']['manifest_revision']!=root['manifest_revision']):
        raise QueryFormatError('request/context identity or revision differs')
    fixture=_decode_query_fixture(root,manifest_bytes,objects_by_sha256)
    start,end=(_u63(request['range'][k]) for k in ('start_ms','end_ms'))
    if not _u63(fixture['declared_range']['start_ms'])<=start<end<=_u63(fixture['declared_range']['end_ms']):
        raise QueryFormatError('query outside explicit fixture coverage')
    result={
        'schema':'market_data.gateway.synthetic-query-result.v1-review1',
        'status':'SYNTHETIC_QUERY_RESULT','source_class':'SYNTHETIC',
        'request_sha256':prepared.request_sha256,'request':request,
        'classification':'SYNTHETIC_FIXTURE_LOCALLY_CHECKED_ONLY',
        'session_classification':'NOT_EVALUATED_BY_PURE_DATA','execution_authority':False,
        'native_authenticated':False,'provider_coverage':'UNKNOWN','provider_gaps':'UNKNOWN',
        'publication':'UNPROVEN','registry':'UNPROVEN','source_completeness':'UNPROVEN',
        'integrity':'LOCAL_HASH_MATCHED_NOT_REPLICA_VERIFIED','committed_revision':None,
        'manifest_sha256':root['manifest_sha256'],'manifest_revision':root['manifest_revision'],
        'dataset_revision':request['dataset_revision'],
        'rows':[row for row in fixture['rows'] if start<=_u63(row[0])<end],
        'cells':[cell for cell in fixture['cells'] if start<=_u63(cell['start_ms'])<end],
    }
    if len(_canonical(result))>1048576:raise QueryFormatError('complete query output byte bound')
    return result
