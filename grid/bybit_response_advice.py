"""Bounded untrusted response advice. No quota, authority, clock or I/O."""
from dataclasses import dataclass
from email.utils import parsedate_to_datetime, format_datetime
import hashlib
import json
import re

_PROFILE = {
    'schema': 'bybit.response-advice.profile.v1',
    'input': 'HTTP status canonical decimal string; <=5 projected header pairs; <=4096 raw error-body bytes',
    'headers': ['date', 'retry-after', 'x-bapi-limit', 'x-bapi-limit-status',
                'x-bapi-limit-reset-timestamp'],
    'header_name_max_ascii_bytes': '64',
    'header_value_max_ascii_bytes': '256', 'body_max_bytes': '4096',
    'json_max_container_depth': '8', 'json_max_nodes_including_keys': '128',
    'json_max_object_members': '32', 'unsigned_header_max': '9007199254740991',
    'reset_timestamp_max_ms': '253402300799999',
    'ret_code_range': '0..2147483647 integer in raw provider JSON, explicitly projected to decimal string',
    'authority': 'UNTRUSTED_ADVICE_ONLY_NEVER_PERMISSION',
    '403': 'exact access too frequent message -> IP ban guidance >=600 seconds and session containment; other403 ambiguous',
    '429': 'HTTP system frequency signal, not an IP/UID allowance',
    '10006': 'API UID/endpoint throttle, not a public-IP budget',
    'retry_after': 'canonical unsigned seconds or exact IMF-fixdate; guidance only, no worker-clock resolution',
    'reset_header': 'endpoint/UID untrusted absolute timestamp, not an IP allowance or authoritative deadline',
    'malformed': 'RAISE_RESPONSE_ADVICE_FORMAT_ERROR_CONSUMER_MUST_FAIL_CLOSED',
    'integration': 'NOT_ADMITTED_NO_CONSUMER_WIRING',
}
_PROFILE_BYTES=json.dumps(_PROFILE,sort_keys=True,separators=(',',':')).encode('ascii')
PROFILE_SHA256=hashlib.sha256(_PROFILE_BYTES).hexdigest()


def profile_bytes(): return _PROFILE_BYTES


class ResponseAdviceFormatError(ValueError):
    """Unusable observation; caller must not turn this into allowance/retry."""


def _fail(message): raise ResponseAdviceFormatError(message)


def _unsigned(value, maximum=9007199254740991):
    if (type(value) is not str or len(value)>19
            or not re.fullmatch(r'0|[1-9][0-9]*',value) or int(value)>maximum):
        _fail('noncanonical/bounded unsigned header')
    return value


def _date(value):
    try:
        d=parsedate_to_datetime(value)
        if not 1970<=d.year<=9999 or format_datetime(d,usegmt=True)!=value:
            _fail('noncanonical IMF-fixdate')
    except (ValueError,TypeError,OverflowError) as exc:
        raise ResponseAdviceFormatError('invalid IMF-fixdate') from exc
    return value


def _pairs(pairs):
    if len(pairs)>32: _fail('body object cap')
    result={}
    for key,value in pairs:
        if key in result or len(key)>64: _fail('duplicate/excess body key')
        result[key]=value
    return result


def _no_float(_): _fail('floating/nonfinite raw JSON not in this projection')


def _body(raw,status):
    if type(raw) is not bytes or len(raw)>4096: _fail('body type/cap')
    if not raw: return None,None
    if status=='403' and raw.lower()==b'access too frequent':
        return None,'access too frequent'
    depth=0;quoted=False;escaped=False
    for char in raw:
        if quoted:
            if escaped: escaped=False
            elif char==92: escaped=True
            elif char==34: quoted=False
        elif char==34: quoted=True
        elif char in (123,91):
            depth+=1
            if depth>8: _fail('body depth cap')
        elif char in (125,93): depth-=1
    try:
        value=json.loads(raw.decode('ascii'),object_pairs_hook=_pairs,
                         parse_float=_no_float,parse_constant=_no_float)
    except (UnicodeError,ValueError,RecursionError) as exc:
        raise ResponseAdviceFormatError('invalid bounded error JSON') from exc
    pending=[value];nodes=0
    while pending:
        item=pending.pop();nodes+=1
        if nodes>128: _fail('body node cap')
        if type(item) is dict:
            pending.extend(item.keys());pending.extend(item.values())
        elif type(item) is list: pending.extend(item)
        elif type(item) is str and any(ord(c)<32 or ord(c)>126 for c in item):
            _fail('body ASCII projection')
    if type(value) is not dict: _fail('expected error object')
    code=value.get('retCode');message=value.get('retMsg')
    if type(code) is not int or not 0<=code<=2147483647: _fail('retCode projection')
    if type(message) is not str or len(message)>256: _fail('retMsg projection')
    return str(code),message


@dataclass(frozen=True)
class ResponseAdvice:
    profile_sha256: str
    http_status: str
    ret_code: str | None
    classification: str
    minimum_backoff_seconds: str | None
    session_action: str
    retry_after_seconds: str | None
    retry_after_http_date: str | None
    endpoint_limit: str | None
    endpoint_remaining: str | None
    endpoint_reset_timestamp_ms: str | None
    response_date: str | None
    body_sha256: str
    header_projection_sha256: str
    authority_status: str = 'UNTRUSTED_ADVICE_ONLY'


def parse_response_advice(http_status,headers,body):
    """Interpret an explicitly bounded projection, never grant scope or retry.

    The transport must preserve original source evidence independently. Unknown
    full-response headers cannot be silently passed here: this API requires an
    explicit allowlisted projection preserving duplicates for rejection.
    Absolute timestamps remain untrusted strings; no clock is read or consulted.
    """
    if type(http_status) is not str or len(http_status)!=3 or not re.fullmatch(r'[1-5][0-9]{2}',http_status):
        _fail('status projection')
    if type(headers) is not list or len(headers)>5: _fail('header projection cap/type')
    fields={}
    for pair in headers:
        if type(pair) is not list or len(pair)!=2: _fail('header pair shape')
        name,value=pair
        if type(name) is not str or type(value) is not str: _fail('header string type')
        if not name or len(name)>64 or any(ord(c)<33 or ord(c)>126 for c in name):
            _fail('header name bounds/grammar')
        name=name.lower()
        if name not in _PROFILE['headers'] or name in fields: _fail('unknown/duplicate header')
        if not value or len(value)>256 or any(ord(c)<32 or ord(c)>126 for c in value) or value!=value.strip():
            _fail('header value bounds/grammar')
        fields[name]=value
    limit=fields.get('x-bapi-limit');remaining=fields.get('x-bapi-limit-status')
    reset=fields.get('x-bapi-limit-reset-timestamp')
    if limit is not None: _unsigned(limit)
    if remaining is not None: _unsigned(remaining)
    if limit is not None and remaining is not None and int(remaining)>int(limit):
        _fail('contradictory endpoint headers')
    if reset is not None: _unsigned(reset,253402300799999)
    date=fields.get('date')
    if date is not None: _date(date)
    retry=fields.get('retry-after');seconds=retry_date=None
    if retry is not None:
        if re.fullmatch(r'[0-9]+',retry): seconds=_unsigned(retry)
        else: retry_date=_date(retry)
    code,message=_body(body,http_status)
    classification='NO_RECOGNIZED_THROTTLE';minimum=None;action='NO_AUTOMATIC_ACTION'
    if http_status=='403':
        classification='FORBIDDEN_AMBIGUOUS'
        if message is not None and message.lower()=='access too frequent':
            classification='HTTP_IP_FREQUENCY_BAN';minimum='600'
            action='REQUIRE_HTTP_SESSION_CONTAINMENT'
    elif http_status=='429': classification='HTTP_SYSTEM_FREQUENCY';minimum='1'
    elif code=='10006': classification='API_UID_ENDPOINT_THROTTLE';minimum='1'
    if seconds is not None and minimum is not None:
        minimum=str(max(int(minimum),int(seconds)))
    return ResponseAdvice(PROFILE_SHA256,http_status,code,classification,minimum,
        action,seconds,retry_date,limit,remaining,reset,date,hashlib.sha256(body).hexdigest(),
        hashlib.sha256(json.dumps(headers,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest())
