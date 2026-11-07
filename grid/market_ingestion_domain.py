"""Exact domain binding for untrusted market-data claims, with no I/O.

This module is not an admitted Control Mux projection or publication adapter.
Its digests identify typed input bytes, never actual storage/authority roots.
"""
from dataclasses import dataclass
import hashlib
import json
import re

from .checkpoint_v3_codec import SCHEMA_SHA256, CheckpointFormatError, parse_claim

INSTRUMENT_DOMAIN = 'bybit.instrument-identity.v1'
CHECKPOINT_DOMAIN = 'unified.historical-checkpoint.v3-review1'
CHECKPOINT_SCHEMA_SHA256 = SCHEMA_SHA256

_INSTRUMENT_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    '$id': 'urn:unified:bybit:instrument-identity:v1',
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'exchange': {'const': 'bybit'},
        'category': {'enum': ['linear', 'spot', 'inverse', 'option']},
        'symbol': {'type': 'string', 'pattern': '^[A-Z0-9][A-Z0-9_-]{0,63}$'},
        'instrument_version': {'type': 'string', 'pattern': '^[1-9][0-9]{0,18}$',
                               'maxLength': 19},
    },
    'required': ['exchange', 'category', 'symbol', 'instrument_version'],
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('ascii')


_INSTRUMENT_SCHEMA_BYTES = _canonical(_INSTRUMENT_SCHEMA)
INSTRUMENT_SCHEMA_SHA256 = hashlib.sha256(_INSTRUMENT_SCHEMA_BYTES).hexdigest()


class DomainUnavailable(RuntimeError):
    """Unknown schema/domain or missing actual authority integration."""


class DomainFormatError(ValueError):
    """Invalid bytes for the explicitly bound supported domain."""


def instrument_schema_bytes():
    """Frozen schema image; executable validation additionally checks u63 range."""
    return _INSTRUMENT_SCHEMA_BYTES


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DomainFormatError('duplicate key')
        out[key] = value
    return out


def _no_number(_):
    raise DomainFormatError('numeric literal forbidden')


def _identity(raw):
    if type(raw) is not bytes or len(raw) > 512:
        raise DomainFormatError('identity bytes limit/type')
    # Identity is one flat object of strings; reject nested containers before
    # invoking the recursive JSON decoder, including hostile small deep inputs.
    if raw.count(b'{') != 1 or b'[' in raw or b']' in raw:
        raise DomainFormatError('identity must be a flat object')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs,
                           parse_int=_no_number, parse_float=_no_number,
                           parse_constant=_no_number)
        if type(value) is not dict or set(value) != set(_INSTRUMENT_SCHEMA['required']):
            raise DomainFormatError('identity fields')
        if any(type(v) is not str for v in value.values()):
            raise DomainFormatError('identity string fields')
        version = value['instrument_version']
        if (value['exchange'] != 'bybit'
                or value['category'] not in ('linear', 'spot', 'inverse', 'option')
                or not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,63}', value['symbol'])
                or not re.fullmatch(r'[1-9][0-9]{0,18}', version)
                or int(version) > 9223372036854775807
                or _canonical(value) != raw):
            raise DomainFormatError('identity grammar/canonical bytes')
        return raw
    except (UnicodeError, json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise DomainFormatError('identity encoding') from exc


@dataclass(frozen=True)
class DomainClaim:
    domain_id: str
    schema_sha256: str
    canonical_bytes: bytes
    content_sha256: str
    instrument_bytes: bytes | None
    dataset_id: str | None
    partition_id: str | None
    validation_status: str = 'VALIDATED_UNTRUSTED_CLAIM'


def decode_domain(domain_id, schema_sha256, raw):
    """Validate explicitly pinned bytes; never silently convert legacy values."""
    if type(domain_id) is not str or type(schema_sha256) is not str:
        raise DomainUnavailable('UNAVAILABLE: exact domain/schema binding required')
    if domain_id == INSTRUMENT_DOMAIN and schema_sha256 == INSTRUMENT_SCHEMA_SHA256:
        instrument = _identity(raw)
        dataset = partition = None
    elif domain_id == CHECKPOINT_DOMAIN and schema_sha256 == CHECKPOINT_SCHEMA_SHA256:
        try:
            claim = parse_claim(raw)
        except CheckpointFormatError as exc:
            raise DomainFormatError('invalid checkpoint claim') from exc
        value = claim.as_dict()
        if claim.commit_status == 'COMMITTED':
            content = value['publication_content']
            instrument = _identity(_canonical(content['instrument_id']))
            dataset, partition = content['dataset_id'], content['partition_id']
        else:
            instrument = dataset = partition = None
    else:
        raise DomainUnavailable('UNAVAILABLE: domain/version/schema not registered')
    return DomainClaim(domain_id, schema_sha256, raw, hashlib.sha256(raw).hexdigest(),
                       instrument, dataset, partition)


def require_authoritative_domain(claim):
    """No actual A2/A4 evidence adapter is available; caller claims cannot admit it."""
    raise DomainUnavailable('UNAVAILABLE: actual authority/publication adapter absent')
