"""Pure synthetic OHLCV request preparation; no query/disclosure adapter.

Local profile only. Neither canonical claims nor their digests prove an admitted
dataset, registry, publication, capability, coverage or historical knowledge.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re

REQUEST_SCHEMA = 'grid.gateway.ohlcv-query.v1-review2'
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
    'schema': 'grid.gateway.synthetic-ohlcv-row.v1-review1',
    'columns': ['open_time_ms', 'open', 'high', 'low', 'close', 'volume', 'turnover'],
    'source_class': 'SYNTHETIC', 'category': 'linear', 'interval_ms': '60000',
    'financial_encoding': 'canonical-exact-decimal-strings',
    'price_unit': 'quote-per-base', 'volume_unit': 'base', 'turnover_unit': 'quote',
})
DATA_SCHEMA_SHA256 = hashlib.sha256(_DATA_SCHEMA_BYTES).hexdigest()
_PROFILE_BYTES = _canonical({
    'schema': 'grid.gateway.synthetic-ohlcv-preparation.v1-review2',
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
    if type(value) is not dict or set(value) != set(keys):
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


def _validate(raw):
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        raise QueryFormatError('bounded bytes required')
    # Bound containers before invoking the recursive JSON parser. This closed
    # profile has exactly five objects, no arrays and no container chars in IDs.
    if raw.count(b'{') != 5 or raw.count(b'}') != 5 or b'[' in raw or b']' in raw:
        raise QueryFormatError('container shape')
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
        if (not start < end <= cutoff <= MAX_UTC_MS or start % 60000
                or end % 60000 or (end - start) // 60000 > MAX_ROWS):
            raise QueryFormatError('range, cutoff or row bound')
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
            'schema': 'grid.gateway.ohlcv-not-executed.v1-review2',
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
    depth = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped: escaped = False
            elif char == 92: escaped = True
            elif char == 34: quoted = False
        elif char == 34: quoted = True
        elif char in (123, 91):
            depth += 1
            if depth > 8: raise QueryFormatError('fixture depth bound')
        elif char in (125, 93):
            depth -= 1
            if depth < 0: raise QueryFormatError('fixture nesting')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs,
                           parse_int=_no_number, parse_float=_no_number,
                           parse_constant=_no_number)
        if _canonical(value) != raw: raise QueryFormatError('fixture canonical bytes')
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise QueryFormatError('fixture encoding') from exc


def decode_synthetic_fixture(manifest_bytes, objects_by_sha256):
    """Check fixed synthetic byte closure, NOT a query or manifest authority.

    Caller supplies already-read bytes. Actual future adapter must also invoke
    admitted A4 decode_manifest and actual A2 permission checks around every IO.
    No store, capability, callback, publication or registry proof is accepted here.
    """
    try:
        return _decode_fixture(manifest_bytes, objects_by_sha256)
    except (KeyError, TypeError, IndexError, RecursionError) as exc:
        raise QueryFormatError('fixture shape/join') from exc


def _decode_fixture(manifest_bytes, objects):
    if type(objects) is not dict or len(objects) != 5:
        raise QueryFormatError('exact five-object closure required')
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
    root = _fixture_json(manifest_bytes, 16384)
    _closed(root, ('schema', 'lineage', 'manifest_revision', 'previous_manifest_sha256',
                   'segments_root_sha256', 'coverage_root_sha256',
                   'dependencies_root_sha256', 'data_schema_sha256'))
    if root['schema'] != 'unified.storage.instrument-manifest.v1-review1':
        raise QueryFormatError('manifest profile')
    revision = _u63(root['manifest_revision'], positive=True)
    if revision == 1:
        if root['previous_manifest_sha256'] is not None: raise QueryFormatError('genesis predecessor')
    else: _string(root['previous_manifest_sha256'], _HASH)
    lineage = root['lineage']
    _closed(lineage, ('schema', 'cluster_id', 'dataset_id', 'source_id', 'partition_id', 'instrument_id', 'data_kind'))
    if (lineage['schema'] != 'unified.storage.manifest-lineage.v1-review1'
            or lineage['data_kind'] != 'normalized'
            or lineage['source_id'] != 'synthetic.gateway.ohlcv.1m.v1'):
        raise QueryFormatError('synthetic lineage profile')
    for key in ('cluster_id', 'dataset_id'): _string(lineage[key], _UUID)
    _string(lineage['partition_id'], r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
    instrument = lineage['instrument_id']
    _closed(instrument, ('exchange', 'category', 'symbol', 'instrument_version'))
    if any(instrument[k] != v for k,v in (('exchange','bybit'),('category','linear'),('symbol','BTCUSDT'))):
        raise QueryFormatError('synthetic instrument')
    _u63(instrument['instrument_version'], positive=True)
    lineage_sha = hashlib.sha256(_canonical(lineage)).hexdigest()
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

    index = record('segments_root_sha256', 16384, 'grid.gateway.synthetic-segment-index.v1-review1',
                   ('data_schema_sha256','interval_ms','declared_range','segments'))
    _closed(index['declared_range'], ('start_ms','end_ms'))
    start, end = (_u63(index['declared_range'][k]) for k in ('start_ms','end_ms'))
    if not start < end <= MAX_UTC_MS or start % 60000 or end % 60000 or (end-start)//60000 > MAX_ROWS:
        raise QueryFormatError('fixture declared range')
    if index['data_schema_sha256'] != DATA_SCHEMA_SHA256 or index['interval_ms'] != '60000':
        raise QueryFormatError('index row profile')
    refs = index['segments']
    if type(refs) is not list or len(refs) != 1: raise QueryFormatError('one segment required')
    ref = refs[0]; _closed(ref, ('sha256','bytes','row_count')); _string(ref['sha256'],_HASH)
    rows_raw = objects[ref['sha256']]
    if _u63(ref['bytes'],positive=True) != len(rows_raw): raise QueryFormatError('segment byte count')
    segment = _fixture_json(rows_raw, 524288)
    _closed(segment, ('schema','source_class','lineage_sha256','data_schema_sha256','interval_ms','rows'))
    if (segment['schema'] != 'grid.gateway.synthetic-row-segment.v1-review1'
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
        if not start <= time < end or time % 60000 or (times and time <= times[-1]):
            raise QueryFormatError('row ordering/range')
        times.append(time)
        values = []
        for text in row[1:]:
            if type(text) is not str or len(text) > 80: raise QueryFormatError('decimal bound')
            _string(text, r'(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?')
            values.append(Decimal(text))
        op,hi,lo,cl,volume,turnover = values
        if not 0 < lo <= min(op,cl) <= max(op,cl) <= hi or volume < 0 or turnover < 0:
            raise QueryFormatError('OHLCV relation')
    coverage = record('coverage_root_sha256', 524288, 'grid.gateway.synthetic-coverage.v1-review1',
                      ('data_schema_sha256','segments_root_sha256','interval_ms','declared_range','cells'))
    if (coverage['data_schema_sha256'] != DATA_SCHEMA_SHA256 or coverage['interval_ms'] != '60000'
            or coverage['segments_root_sha256'] != root['segments_root_sha256']
            or coverage['declared_range'] != index['declared_range']):
        raise QueryFormatError('coverage profile/joins')
    cells = coverage['cells']
    if type(cells) is not list or len(cells) != (end-start)//60000 or len(cells) > MAX_ROWS:
        raise QueryFormatError('coverage cells')
    actual_present = []
    rules = {'PRESENT':('FIXTURE_GENERATED','NOT_APPLICABLE'),
             'GAP':('FIXTURE_OMISSION','UNKNOWN'), 'UNOBSERVED':('FIXTURE_UNOBSERVED','UNKNOWN')}
    for i, cell in enumerate(cells):
        _closed(cell, ('start_ms','end_ms','disposition','reason','recoverability'))
        expected = start+i*60000
        if _u63(cell['start_ms']) != expected or _u63(cell['end_ms']) != expected+60000:
            raise QueryFormatError('coverage cell ordering')
        disposition = cell['disposition']
        if type(disposition) is not str or disposition not in rules or (cell['reason'],cell['recoverability']) != rules[disposition]:
            raise QueryFormatError('coverage disposition')
        if disposition == 'PRESENT': actual_present.append(expected)
    if times != actual_present: raise QueryFormatError('explicit coverage does not match actual rows')
    dependencies = record('dependencies_root_sha256', 16384, 'grid.gateway.synthetic-dependencies.v1-review1', ('objects',))
    roles = [('data_schema',DATA_SCHEMA_SHA256),('rows',ref['sha256']),
             ('segment_index',root['segments_root_sha256']),('coverage',root['coverage_root_sha256'])]
    expected_deps = [{'role':role,'sha256':key,'bytes':str(len(objects[key]))} for role,key in roles]
    if dependencies['objects'] != expected_deps or set(objects) != {key for _,key in roles}|{root['dependencies_root_sha256']}:
        raise QueryFormatError('exact dependency closure')
    return {'classification':'SYNTHETIC_FIXTURE_LOCALLY_CHECKED_ONLY',
            'provider_coverage':'UNKNOWN','provider_gaps':'UNKNOWN',
            'publication':'UNPROVEN','registry':'UNPROVEN','execution_authority':False,
            'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
            'manifest_revision':root['manifest_revision'],'lineage':lineage,
            'data_schema_sha256':DATA_SCHEMA_SHA256,'declared_range':index['declared_range'],
            'rows':rows,'cells':cells}
