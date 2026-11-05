"""MODELED_CONSUL counterexamples; not persistent consensus/runtime proof."""
import asyncio
import base64
import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest

from grid.coordination import CoordinationUnavailable, canonical
from grid.coordination_budget_anchor import (
    BudgetAnchor, AnchorVersion, ConsulBudgetAnchor, AnchorConflict, AnchorRejected,
)


def fixture():
    spec = importlib.util.spec_from_file_location('anchor_modeled_consul_fixture',
        Path(__file__).with_name('test_coordination_commands.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    authority, client, store, state = module.fixture()
    original_request = authority._request
    async def request(method, path, **kwargs):
        result = await original_request(method, path, **kwargs)
        if method == 'GET' and path.startswith('/v1/kv/') and type(result) is list:
            # The reused semantic fixture stores decoded objects. Actual Consul
            # preserves submitted canonical bytes; model that wire representation.
            for row in result:
                value = json.loads(base64.b64decode(row['Value']))
                row['Value'] = base64.b64encode(canonical(value)).decode()
        return result
    authority._request = request
    return authority, client, store, state


def anchor(revision=1, offset=1, **changes):
    values = dict(installation_id='install-1', meter_id='http',
                  store_generation_sha256='a' * 64, revision=revision,
                  offset=offset, journal_sha256='b' * 64)
    values.update(changes)
    return BudgetAnchor(**values)


def bridge(authority, **kwargs):
    return ConsulBudgetAnchor(authority, 'install-1', 'http', 'a' * 64, **kwargs)


def test_create_read_advance_and_exact_reconciliation():
    async def scenario():
        authority, client, store, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            meter = bridge(authority)
            assert await meter.read() is None
            first = await meter.compare_and_swap(lease, None, anchor())
            assert first.status == 'COMMITTED' and type(first.version) is AnchorVersion
            assert first.version.consensus_modify_index == 11
            assert first.version.anchor == anchor()
            assert await meter.read() == first.version
            next_anchor = anchor(2, 9, journal_sha256='c' * 64)
            second = await meter.compare_and_swap(lease, first.version, next_anchor)
            assert second.status == 'COMMITTED' and second.version.anchor == next_anchor
            assert second.version.consensus_modify_index > first.version.consensus_modify_index
            assert (await meter.reconcile(next_anchor)).version == second.version
            assert (await meter.reconcile(anchor())).status == 'UNKNOWN'
            assert state['transactions'] == 2
    asyncio.run(scenario())


def test_lost_commit_response_reconciles_same_anchor_without_credit_or_rebase():
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            meter = bridge(authority)
            state['lost_response'] = True
            result = await meter.compare_and_swap(lease, None, anchor())
            assert result.status in ('UNKNOWN', 'COMMITTED')
            reconciled = await meter.reconcile(anchor())
            assert reconciled.status == 'COMMITTED'
            duplicate = await meter.compare_and_swap(lease, None, anchor())
            assert duplicate.version == reconciled.version
            assert state['transactions'] == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('changes', [dict(revision=True), dict(offset=True), dict(offset=0),
    dict(revision=0), dict(offset=2**53), dict(revision=2**53), dict(meter_id='bad/path'),
    dict(installation_id=':bad'), dict(store_generation_sha256='bad'), dict(journal_sha256='B'*64)])
def test_strict_anchor_fields(changes):
    with pytest.raises(AnchorRejected):
        anchor(**changes)


@pytest.mark.parametrize('changes', [dict(revision=3,offset=2), dict(revision=2,offset=1),
    dict(revision=2,offset=0), dict(revision=2,offset=3,meter_id='other'),
    dict(revision=2,offset=3,installation_id='other'),
    dict(revision=2,offset=3,store_generation_sha256='d'*64)])
def test_no_revision_gap_refund_reset_or_scope_takeover(changes):
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            meter = bridge(authority)
            first = await meter.compare_and_swap(lease, None, anchor())
            with pytest.raises((AnchorRejected, AnchorConflict)):
                await meter.compare_and_swap(lease, first.version, anchor(**changes))
            assert state['transactions'] == 1
    asyncio.run(scenario())


def test_forged_expected_version_cannot_advance_existing_anchor():
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            meter = bridge(authority)
            first = await meter.compare_and_swap(lease, None, anchor())
            forged = AnchorVersion(anchor(80, 500), first.version.consensus_modify_index)
            with pytest.raises(AnchorConflict):
                await meter.compare_and_swap(lease, forged, anchor(81, 501))
            assert state['transactions'] == 1
    asyncio.run(scenario())


def test_no_quorum_unknown_and_read_is_not_missing():
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            meter = bridge(authority)
            state['offline'] = True
            result = await meter.compare_and_swap(lease, None, anchor())
            assert result.status == 'UNKNOWN' and result.version is None
            with pytest.raises(CoordinationUnavailable):
                await meter.read()
            assert (await meter.reconcile(anchor())).status == 'UNKNOWN'
            assert state['transactions'] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('changes', [dict(private='secret'), dict(schema='other'),
    dict(store_generation_sha256='d'*64), dict(offset=True)])
def test_malformed_storage_never_returns_missing_or_trusted_version(changes):
    async def scenario():
        authority, client, store, _ = fixture()
        async with client:
            meter = bridge(authority)
            record = dict(schema='grid.network-budget-anchor.v1', **dataclasses.asdict(anchor()))
            record.update(changes)
            store[meter.key] = (9, record)
            with pytest.raises(AnchorRejected):
                await meter.read()
    asyncio.run(scenario())


def test_source_revocation_and_lease_loss_before_disclosure_deny():
    class Guard:
        active = True
        def require_current(self):
            if not self.active:
                raise AnchorRejected('SOURCE_REVOKED')
            return True
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            guard = Guard()
            lease = await authority.acquire('LS5')
            meter = bridge(authority, source_guard=guard)
            guard.active = False
            with pytest.raises(AnchorRejected):
                await meter.compare_and_swap(lease, None, anchor())
            guard.active = True
            state['index'] = 12
            # The modeled lock remains index10; invalidate the exact issued lease
            # locally rather than treating a user-supplied token as authority.
            authority._deadlines[lease.session_id] = 0
            result = await meter.compare_and_swap(lease, None, anchor())
            assert result.status == 'UNKNOWN' and result.version is None
            assert state['transactions'] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('raw', [b'{"schema":"x","schema":"y"}', b'{"x":NaN}',
    b'{"x":1e999}', b' ' * 4097, b'[' * 1000 + b'0' + b']' * 1000, b'\xff'],
    ids=['duplicates','nonfinite','overflow','byte-bound','depth','utf8'])
def test_untrusted_anchor_wire_is_bounded_and_duplicate_free(raw):
    async def scenario():
        authority, client, _, _ = fixture()
        async with client:
            meter = bridge(authority)
            async def request(*args, **kwargs):
                return [dict(Key=meter.key, ModifyIndex=12, Value=base64.b64encode(raw).decode())]
            authority._request = request
            with pytest.raises(AnchorRejected):
                await meter.read()
    asyncio.run(scenario())


def test_forged_lease_value_does_not_grant_budget_mutation():
    from grid.coordination import ConsulLease
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            forged = ConsulLease(lease.owner, lease.session_id, lease.token)
            result = await bridge(authority).compare_and_swap(forged, None, anchor())
            assert result.status == 'UNKNOWN' and result.version is None
            assert state['transactions'] == 0
    asyncio.run(scenario())


def test_scope_and_source_are_rechecked_after_actual_commit_before_publication():
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            class Guard:
                def require_current(self):
                    if state['transactions']:
                        raise AnchorRejected('REVOKED_AFTER_COMMIT')
                    return True
            lease = await authority.acquire('LS5')
            with pytest.raises(AnchorRejected, match='REVOKED_AFTER_COMMIT'):
                await bridge(authority, source_guard=Guard()).compare_and_swap(lease, None, anchor())
            assert state['transactions'] == 1
            assert (await bridge(authority).reconcile(anchor())).status == 'COMMITTED'
    asyncio.run(scenario())


@pytest.mark.parametrize('same_anchor', [False, True])
def test_cas409_race_reconciles_only_exact_anchor(same_anchor):
    from grid.coordination import CoordinationLost
    async def scenario():
        authority, client, store, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            meter = bridge(authority)
            original = authority._request
            competing = anchor() if same_anchor else anchor(offset=7, journal_sha256='c'*64)
            async def request(method, path, **kwargs):
                if method == 'PUT' and path == '/v1/txn':
                    store[meter.key] = (12, dict(schema='grid.network-budget-anchor.v1', **dataclasses.asdict(competing)))
                    raise CoordinationLost('modeled CAS409')
                return await original(method, path, **kwargs)
            authority._request = request
            if same_anchor:
                result = await meter.compare_and_swap(lease, None, anchor())
                assert result.status == 'COMMITTED' and result.version.consensus_modify_index == 12
            else:
                with pytest.raises(AnchorConflict):
                    await meter.compare_and_swap(lease, None, anchor())
                assert (await meter.read()).anchor == competing
            assert state['transactions'] == 0
    asyncio.run(scenario())


def test_source_revocation_during_final_lease_rpc_blocks_publication():
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            class Guard:
                active = True
                def require_current(self):
                    if not self.active:
                        raise AnchorRejected('REVOKED_DURING_LEASE_RPC')
                    return True
            guard = Guard()
            lease = await authority.acquire('LS5')
            original = authority.validate
            async def validate(current):
                valid = await original(current)
                if state['transactions']:
                    guard.active = False
                return valid
            authority.validate = validate
            with pytest.raises(AnchorRejected, match='REVOKED_DURING_LEASE_RPC'):
                await bridge(authority, source_guard=guard).compare_and_swap(lease, None, anchor())
    asyncio.run(scenario())
