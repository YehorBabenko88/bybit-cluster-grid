"""Pure, bounded DATA_ONLY planning; never an admission or dispatch interface.

No clocks, transport, registry lookup, reservation, quota debit or authority.
Even a manually constructed result is data, not a permission/intent/receipt.
"""
from dataclasses import dataclass
import hashlib
import json
import re


WIRE_SHA256 = '16606dee585398ae6d92139ffc1cf2ed37a4d2e08759aaa08f0c3b85958b8049'
POLICY_SHA256 = '973f84f87de066d6686dfbe1177dc583637fa819aa21f988303e3a649abae3f1'
POLICY_BODY_DIGEST = 'b3ea69e77ef17b3cd2a894f16df32cb1caba3178efb8814800d4017507e15ca3'
_PREFIX = 'bybit.public.linear.'
_OPERATIONS = frozenset(_PREFIX + suffix for suffix in (
    'instruments.v1', 'kline.1m.v1', 'ws.connect.v1', 'ws.ping.v1',
    'ws.subscribe.v1', 'ws.unsubscribe.v1'))
_PROJECTION = ('exchange', 'environment', 'regional_host_group', 'method',
               'path_or_ws_action', 'category', 'endpoint_class', 'credential_scope_reference')
_U63 = 9223372036854775807
_UTC_MAX = 253402300799999


class PlanFormatError(ValueError):
    """Closed refusal category: no partial plan, fallback or external effect."""


@dataclass(frozen=True, slots=True)
class PreparedBybitRequestPlan:
    canonical_request_bytes: bytes
    canonical_plan_bytes: bytes

    def as_dict(self) -> dict:
        """Return detached data; this object is never an authorization proof."""
        return json.loads(self.canonical_plan_bytes)


def _need(condition, reason):
    if not condition:
        raise PlanFormatError(reason)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _closed(value, keys):
    _need(type(value) is dict and set(value) == set(keys), 'closed object required')


def _pairs(items):
    value = {}
    for key, item in items:
        _need(key not in value, 'duplicate JSON key')
        value[key] = item
    return value


def _no_number(_value):
    raise PlanFormatError('numeric JSON literals prohibited')


def _scan_request(raw):
    """Bound containers/tokens before the recursive JSON decoder is entered.

    Counts keys as well as values, a conservative bound on decoded nodes.
    JSON syntax and exact encoding are checked separately after this scan.
    """
    stack, nodes, quoted, escaped, token = [], 0, False, False, False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
            continue
        if char == 34:
            quoted, token = True, False
            nodes += 1
        elif char in (123, 91):
            stack.append(char)
            nodes += 1
            token = False
            _need(len(stack) <= 8, 'container depth exceeded')
        elif char in (125, 93):
            _need(bool(stack) and stack.pop() == (123 if char == 125 else 91), 'container mismatch')
            token = False
        elif char in (44, 58, 32, 9, 10, 13):
            token = False
        elif not token:
            nodes += 1
            token = True
        _need(nodes <= 4096, 'node bound exceeded')
    _need(not quoted and not stack, 'unfinished JSON')


def _request(raw):
    _scan_request(raw)
    try:
        text = raw.decode('ascii')
        value = json.loads(text, object_pairs_hook=_pairs, parse_int=_no_number,
                           parse_float=_no_number, parse_constant=_no_number)
        _need(_canonical(value) == raw, 'noncanonical request encoding')
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PlanFormatError('invalid request JSON') from exc
    _closed(value, ('schema', 'wire_profile_sha256', 'policy_raw_sha256',
                    'operation_id', 'requested_priority', 'instruments', 'payload'))
    _need(value['schema'] == 'grid.bybit.local-request-plan.v1-review1', 'unknown request schema')
    _need(value['wire_profile_sha256'] == WIRE_SHA256
          and value['policy_raw_sha256'] == POLICY_SHA256, 'request profile binding')
    _need(type(value['operation_id']) is str and value['operation_id'] in _OPERATIONS,
          'unsupported operation')
    _need(type(value['requested_priority']) is str, 'priority string required')
    return value


def _profiles(wire_raw, policy_raw):
    # Caller has preflighted ALL THREE inputs before reaching ANY hash/decode.
    _need(hashlib.sha256(wire_raw).hexdigest() == WIRE_SHA256, 'wire raw pin')
    _need(hashlib.sha256(policy_raw).hexdigest() == POLICY_SHA256, 'policy raw pin')
    try:
        wire = json.loads(wire_raw, object_pairs_hook=_pairs)
        policy = json.loads(policy_raw, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PlanFormatError('invalid pinned profile') from exc
    _need(wire['schema'] == 'unified.bybit-egress-wire-contract.v2-review2'
          and policy['schema'] == 'unified.bybit-cost-policy.v1', 'profile schema')
    _need(wire['policy_binding']['candidate_file_sha256'] == POLICY_SHA256
          and wire['policy_binding']['candidate_body_digest'] == POLICY_BODY_DIGEST,
          'wire policy binding')
    body = {key: value for key, value in policy.items() if key != 'digest'}
    _need(policy['digest'] == POLICY_BODY_DIGEST
          and hashlib.sha256(_canonical(body)).hexdigest() == POLICY_BODY_DIGEST,
          'policy body digest')
    _need(policy['operation_digest_fields'] == list(_PROJECTION)
          and wire['operation_projection'] == list(_PROJECTION), 'projection binding')
    activation = policy['activation']
    _need(activation['effective_from_utc'] is None
          and activation['effective_until_utc'] is None, 'disabled activation only')
    operations = policy['operations']
    _need(type(operations) is list and len(operations) == 6, 'six descriptors required')
    by_id = {}
    for operation in operations:
        identity = operation['operation_id']
        _need(identity in _OPERATIONS and identity not in by_id, 'descriptor identity')
        _need(operation['enabled'] is False and operation['exchange'] == 'bybit'
              and operation['category'] == 'linear' and operation['environment'] == 'mainnet'
              and operation['credential_scope_reference'] is None, 'disabled public descriptor only')
        by_id[identity] = operation
    _need(set(by_id) == _OPERATIONS, 'descriptor set')
    return by_id


def _decimal(value, minimum, maximum):
    _need(type(value) is str and len(value) <= 19
          and re.fullmatch(r'(?:0|[1-9][0-9]*)', value) is not None,
          'canonical decimal string required')
    number = int(value)
    _need(minimum <= number <= maximum, 'decimal bounds')
    return number


def _instruments(value):
    _need(type(value) is list and len(value) <= 100, 'instrument count')
    identities, symbols = set(), set()
    for item in value:
        _closed(item, ('exchange', 'category', 'symbol', 'instrument_version'))
        _need(item['exchange'] == 'bybit' and item['category'] == 'linear', 'instrument market')
        symbol = item['symbol']
        _need(type(symbol) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,63}', symbol) is not None,
              'instrument symbol')
        _decimal(item['instrument_version'], 1, _U63)
        identity = (item['exchange'], item['category'], symbol, item['instrument_version'])
        _need(identity not in identities and symbol not in symbols, 'duplicate or ambiguous instrument')
        identities.add(identity)
        symbols.add(symbol)
    return symbols


def _action(operation, *, query=None, body=None):
    return dict(method=operation['method'], host_group=operation['regional_host_group'],
                path_or_action=operation['path_or_ws_action'], query=query,
                body_ascii=None if body is None else _canonical(body).decode('ascii'))


def _actions(value, operation, symbols):
    payload, instruments = value['payload'], value['instruments']
    suffix = value['operation_id'][len(_PREFIX):]
    if suffix == 'instruments.v1':
        _need(not instruments, 'catalog takes no instrument')
        _closed(payload, ('limit', 'cursor'))
        _decimal(payload['limit'], 1, 1000)
        cursor = payload['cursor']
        _need(cursor is None or (type(cursor) is str and 1 <= len(cursor) <= 1024
                                and all(32 <= ord(char) <= 126 for char in cursor)), 'opaque cursor')
        query = dict(category='linear', limit=payload['limit'])
        if cursor is not None:
            query['cursor'] = cursor
        return [_action(operation, query=query)]
    if suffix == 'kline.1m.v1':
        _need(len(instruments) == 1, 'kline requires one instrument')
        _closed(payload, ('interval', 'range', 'limit'))
        _need(payload['interval'] == '1', 'one minute interval only')
        _decimal(payload['limit'], 1, 1000)
        window = payload['range']
        _closed(window, ('start_ms', 'end_ms'))
        start = _decimal(window['start_ms'], 0, _UTC_MAX)
        end = _decimal(window['end_ms'], 0, _UTC_MAX)
        _need(start < end and start % 60000 == 0 and end % 60000 == 0
              and end - start <= 1000 * 60000, 'aligned bounded half-open range')
        return [_action(operation, query=dict(category='linear', symbol=instruments[0]['symbol'],
                interval='1', start=window['start_ms'], end=str(end - 1), limit=payload['limit']))]
    if suffix in ('ws.connect.v1', 'ws.ping.v1'):
        _need(not instruments, 'connection control takes no instruments')
        _closed(payload, ())
        return [_action(operation, body={'op': 'ping'} if suffix == 'ws.ping.v1' else None)]
    _need(suffix in ('ws.subscribe.v1', 'ws.unsubscribe.v1'), 'unsupported action')
    _need(1 <= len(instruments) <= 100, 'topic instrument count')
    _closed(payload, ('topics',))
    topics = payload['topics']
    _need(type(topics) is list and 1 <= len(topics) <= 100, 'topic count')
    seen, used = set(), set()
    for topic in topics:
        _need(type(topic) is str and len(topic) <= 80, 'topic string')
        match = re.fullmatch(r'(?:publicTrade|orderbook\.50|tickers)\.([A-Z0-9][A-Z0-9_-]{0,63})', topic)
        _need(match is not None, 'unsupported topic')
        symbol = match.group(1)
        _need(symbol in symbols and topic not in seen, 'unknown or duplicate topic')
        seen.add(topic)
        used.add(symbol)
    _need(used == symbols, 'unused instrument identity')
    result = []
    for offset in range(0, len(topics), 10):
        args = topics[offset:offset + 10]
        _need(len(_canonical(args)) <= 20000, 'args byte bound')
        result.append(_action(operation, body={'op': operation['path_or_ws_action'], 'args': args}))
    return result


def prepare_bybit_request_plan(request_bytes: bytes, *, wire_contract_bytes: bytes,
                              provider_policy_bytes: bytes) -> PreparedBybitRequestPlan:
    """Prepare immutable local data only. Every actual attempt needs fresh admission.

    minimum_fresh_attempts is a lower-bound DATA count, never cost/debit/quota or
    slot admission. Identity is structural, not registry proof. Digests are not
    intent/idempotency/native-attempt/receipt. No consumer or authority is called.
    """
    for raw, maximum in ((request_bytes, 32768), (wire_contract_bytes, 65536),
                         (provider_policy_bytes, 65536)):
        _need(type(raw) is bytes and 0 < len(raw) <= maximum, 'byte preflight bounds')
    operations = _profiles(wire_contract_bytes, provider_policy_bytes)
    value = _request(request_bytes)
    operation = operations[value['operation_id']]
    _need(value['requested_priority'] in operation['allowed_priority'], 'descriptor priority')
    symbols = _instruments(value['instruments'])
    actions = _actions(value, operation, symbols)
    plan = dict(schema='grid.bybit.data-only-plan.v1-review1', state='DATA_ONLY_NOT_ADMITTED',
                request_sha256=hashlib.sha256(request_bytes).hexdigest(),
                wire_profile_sha256=WIRE_SHA256, policy_raw_sha256=POLICY_SHA256,
                policy_body_digest=POLICY_BODY_DIGEST, operation_id=value['operation_id'],
                operation_digest=hashlib.sha256(_canonical({k: operation[k] for k in _PROJECTION})).hexdigest(),
                requested_priority=value['requested_priority'], instrument_ids=value['instruments'],
                operation_enabled=False, activation_from_utc=None, activation_until_utc=None,
                requires_owned_slot=operation['requires_owned_slot'], connection_state='UNVERIFIED',
                minimum_fresh_attempts=str(len(actions)), actions=actions,
                quota_reserved=False, consume_performed=False, send_permission=False)
    encoded = _canonical(plan)
    _need(len(encoded) <= 32768, 'whole plan byte bound')
    return PreparedBybitRequestPlan(request_bytes, encoded)
