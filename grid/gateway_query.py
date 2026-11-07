"""Pure synthetic OHLCV request preparation; no query/disclosure adapter.

Local profile only. Neither canonical claims nor their digests prove an admitted
dataset, registry, publication, capability, coverage or historical knowledge.
"""
from dataclasses import dataclass
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
