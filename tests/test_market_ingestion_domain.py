"""Domain validation only; no actual publication/provider qualification."""
import hashlib
import importlib
import json
from pathlib import Path

import pytest


def domain():
    return importlib.import_module('grid.market_ingestion_domain')


def wire(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':')).encode('ascii')


def identity(category='linear', version='1', symbol='BTCUSDT'):
    return dict(exchange='bybit', category=category, symbol=symbol,
                instrument_version=version)


def test_markets_and_relisted_incarnations_have_distinct_typed_identity_digests():
    d = domain()
    values = [identity(c, v) for c in ('linear', 'spot', 'inverse', 'option')
              for v in ('1', '2')]
    claims = [d.decode_domain(d.INSTRUMENT_DOMAIN, d.INSTRUMENT_SCHEMA_SHA256,
                              wire(v)) for v in values]
    assert len({c.content_sha256 for c in claims}) == 8
    assert all(c.validation_status == 'VALIDATED_UNTRUSTED_CLAIM' for c in claims)
    assert all(c.canonical_bytes == wire(v) for c, v in zip(claims, values))


@pytest.mark.parametrize('field,value', [
    ('instrument_version', 1), ('instrument_version', True),
    ('instrument_version', '01'), ('instrument_version', '0'),
    ('instrument_version', '9223372036854775808'), ('symbol', 'btcusdt'),
    ('category', 'futures'), ('exchange', 'BYBIT'), ('market', 'linear'),
    ('symbol', 'BTC/USDT'), ('symbol', '\u0410'), ('instrument_version', None)])
def test_identity_rejects_numeric_alias_unknown_market_and_unknown_fields(field, value):
    d = domain(); v = identity(); v[field] = value
    with pytest.raises(d.DomainFormatError):
        d.decode_domain(d.INSTRUMENT_DOMAIN, d.INSTRUMENT_SCHEMA_SHA256, wire(v))


@pytest.mark.parametrize('raw', [
    b'{}', b'[]', b'null', b' '*513,
    b'{"exchange":"bybit","exchange":"bybit"}',
    wire(identity()) + b'\n', wire(identity()).replace(b'BTCUSDT', b'BTC\\u0055SDT')])
def test_identity_rejects_noncanonical_or_oversized_input(raw):
    d = domain()
    with pytest.raises(d.DomainFormatError):
        d.decode_domain(d.INSTRUMENT_DOMAIN, d.INSTRUMENT_SCHEMA_SHA256, raw)


@pytest.mark.parametrize('name', ['market-ingestion.v0', 'dataset-manifest.v1',
                                 'storage-publication.v1', 'integrity-summary.v1'])
def test_unknown_or_unadmitted_domains_are_unavailable(name):
    d = domain()
    with pytest.raises(d.DomainUnavailable):
        d.decode_domain(name, '0'*64, wire(identity()))


def test_schema_hash_mismatch_is_unavailable_not_coerced():
    d = domain()
    with pytest.raises(d.DomainUnavailable):
        d.decode_domain(d.INSTRUMENT_DOMAIN, '0'*64, wire(identity()))
    assert hashlib.sha256(d.instrument_schema_bytes()).hexdigest() == d.INSTRUMENT_SCHEMA_SHA256


def test_checkpoint_delegates_frozen_codec_and_preserves_claim_lineage():
    d = domain()
    raw = (Path(__file__).parent/'fixtures/agent3-checkpoint-v3/confirmed-unknown-time.canonical.json').read_bytes()
    c = d.decode_domain(d.CHECKPOINT_DOMAIN, d.CHECKPOINT_SCHEMA_SHA256, raw)
    v = json.loads(raw)
    assert c.canonical_bytes == raw
    assert c.content_sha256 == hashlib.sha256(raw).hexdigest()
    assert c.validation_status == 'VALIDATED_UNTRUSTED_CLAIM'
    assert c.dataset_id == v['publication_content']['dataset_id']
    assert c.partition_id == v['publication_content']['partition_id']
    assert c.instrument_bytes == wire(v['publication_content']['instrument_id'])
    with pytest.raises(d.DomainUnavailable): d.require_authoritative_domain(c)


def test_checkpoint_unconfirmed_variant_does_not_fabricate_lineage():
    d = domain()
    raw = (Path(__file__).parent/'fixtures/agent3-checkpoint-v3/unconfirmed.canonical.json').read_bytes()
    c = d.decode_domain(d.CHECKPOINT_DOMAIN, d.CHECKPOINT_SCHEMA_SHA256, raw)
    assert c.dataset_id is None and c.partition_id is None and c.instrument_bytes is None
    with pytest.raises(d.DomainUnavailable): d.require_authoritative_domain(c)


def test_caller_objects_and_boolean_cannot_promote_domain():
    d = domain()
    for value in (True, {'verified': True}, object()):
        with pytest.raises(d.DomainUnavailable): d.require_authoritative_domain(value)


def test_frozen_registry_and_schema_match_executable_binding():
    d = domain(); fixtures = Path(__file__).parent/'fixtures/agent3-market-domain'
    assert (fixtures/'instrument-identity.schema.json').read_bytes() == d.instrument_schema_bytes()
    registry = json.loads((fixtures/'registry.json').read_bytes())
    entries = {row['domain_id']: row for row in registry['domains']}
    assert entries[d.INSTRUMENT_DOMAIN]['schema_sha256'] == d.INSTRUMENT_SCHEMA_SHA256
    assert entries[d.CHECKPOINT_DOMAIN]['schema_sha256'] == d.CHECKPOINT_SCHEMA_SHA256
    assert registry['admission'] == 'PENDING_PEER_ACK_NOT_MUX_DATA_ADMISSION'


def test_ten_instruments_preserve_exact_identity_without_symbol_only_key():
    d = domain()
    claims = [d.decode_domain(d.INSTRUMENT_DOMAIN, d.INSTRUMENT_SCHEMA_SHA256,
                             wire(identity(symbol=f'TEST{i}USDT'))) for i in range(10)]
    assert len({c.instrument_bytes for c in claims}) == 10
    assert all(c.dataset_id is None for c in claims)
