"""Read-only canonical v1 decoding for historical bytes; no recorder or writer API."""
"""Opt-in bounded application-payload observations; no sender/store/authority.

The sink is separately owned and admitted. These local readbacks are not native
receipts, hard quotas, source authentication, or publication checkpoints.
"""
__all__ = ("decode_v1_observation",)

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import time
import uuid

U63 = 2**63-1
KEYS = frozenset(('schema','instrument','producer_source_revision','source_kind',
    'endpoint','connection_id','observation_index','kind','received_at_utc',
    'received_monotonic_ns','payload_kind','payload_sha256','payload_bytes',
    'frame_metadata_sha256','previous_metadata_sha256','exchange_event_at_utc',
    'sequence','update_id','reason','publication'))
REASONS = {
    'frame': (None,), 'validated': (None,),
    'disconnect': ('transport_closed','transport_error','cancelled','normal_stop'),
    'gap_observation': ('sequence_invalid','buffer_pressure','frame_oversize',
        'restart_unknown','storage_failure','frame_invalid'),
    'resync': ('initial_snapshot','after_gap','source_restart'),
}

class _HistoricalCaptureError(ValueError):
    """Terminal refusal for an opted-in raw profile; never reconnect around it."""

def _need(value):
    if not value: raise _HistoricalCaptureError('RAW_CAPTURE_INVALID_OR_UNAVAILABLE')

def _match(value, pattern):
    return type(value) is str and re.fullmatch(pattern,value,re.ASCII) is not None

def _number(value, positive=False):
    _need(_match(value,r'0|[1-9][0-9]{0,18}'))
    _need(int(value)<=U63 and (not positive or int(value)>0))
    return value

def _sha(value, nullable=False):
    _need((nullable and value is None) or _match(value,r'[0-9a-f]{64}'))

def _utc(value):
    _need(_match(value,r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{3}Z'))
    try: dt=datetime.fromisoformat(value[:-1]+'+00:00')
    except ValueError: raise _HistoricalCaptureError('RAW_CAPTURE_INVALID_UTC') from None
    _need(dt.isoformat(timespec='milliseconds').replace('+00:00','Z')==value)
    return value

def _identity(value):
    _need(type(value) is dict and set(value)=={'exchange','category','symbol','instrument_version'})
    _need(value['exchange']=='bybit' and value['category']=='linear')
    _need(_match(value['symbol'],r'[A-Z0-9][A-Z0-9_-]{0,63}'))
    _number(value['instrument_version'],True)

def _encode_v1(value):
    """Closed lexical/calendar/cross-field validation, independent of schema."""
    _need(type(value) is dict and set(value)==KEYS)
    _need(value['schema']=='market_data.raw-capture-observation.v1-review1')
    _identity(value['instrument'])
    _need(_match(value['producer_source_revision'],r'[0-9a-f]{40}'))
    _need(value['source_kind'] in ('SYNTHETIC','PUBLIC_PROVIDER_OBSERVED_UNAUTHENTICATED'))
    endpoint='synthetic://bybit/linear' if value['source_kind']=='SYNTHETIC' else 'wss://stream.bybit.com/v5/public/linear'
    _need(value['endpoint']==endpoint)
    _need(_match(value['connection_id'],r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'))
    _number(value['observation_index'],True); _number(value['received_monotonic_ns'])
    _utc(value['received_at_utc'])
    if value['exchange_event_at_utc'] is not None: _utc(value['exchange_event_at_utc'])
    for key in ('sequence','update_id'):
        if value[key] is not None: _number(value[key])
    for key in ('payload_sha256','frame_metadata_sha256','previous_metadata_sha256'): _sha(value[key],True)
    _number(value['payload_bytes']); _need(int(value['payload_bytes'])<=1048576)
    kind=value['kind']; _need(type(kind) is str and kind in REASONS)
    _need(value['reason'] in REASONS[kind] and value['publication']=='LOCAL_UNATTESTED')
    if kind=='frame':
        _need(value['payload_kind'] in ('TEXT_UTF8_REENCODED_NOT_WIRE','BINARY_APPLICATION_PAYLOAD'))
        _sha(value['payload_sha256'])
        _need(all(value[key] is None for key in ('frame_metadata_sha256','exchange_event_at_utc','sequence','update_id')))
    else:
        _need(value['payload_kind']=='NONE' and value['payload_sha256'] is None and value['payload_bytes']=='0')
    if kind in ('validated','resync'): _sha(value['frame_metadata_sha256'])
    try: raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (TypeError,ValueError,RecursionError): raise _HistoricalCaptureError('RAW_CAPTURE_INVALID_METADATA') from None
    _need(0<len(raw)<=16384)
    return raw

def decode_v1_observation(raw):
    _need(type(raw) is bytes and 0<len(raw)<=16384)
    def pairs(items):
        out={}
        for key,value in items:
            _need(key not in out); out[key]=value
        return out
    def no_number(_): raise _HistoricalCaptureError('RAW_CAPTURE_NUMERIC_TOKEN')
    try: value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
                          parse_int=no_number,parse_float=no_number,parse_constant=no_number)
    except (ValueError,UnicodeError,RecursionError): raise _HistoricalCaptureError('RAW_CAPTURE_INVALID_METADATA') from None
    _need(_encode_v1(value)==raw)
    return value

