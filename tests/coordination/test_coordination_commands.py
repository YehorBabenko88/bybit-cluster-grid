"""Offline protocol counterexamples; these are NOT consensus durability proof."""
import asyncio
import base64
import copy
import json
import uuid

import httpx
import pytest

from grid.coordination import ConsulConfig, ConsulSessionAuthority
from grid.coordination_commands import CoordinationCommands, CurrentPrincipal, CommandDenied, parse_command, validate_receipt

GEN = str(uuid.UUID(int=7))


class Provider:
    active = True

    async def require_current(self, context, action, aggregate_id):
        if not self.active or context != 'verified-test-context':
            raise CommandDenied('unauthorized')
        return CurrentPrincipal('human-test', 3, 'HUMAN', frozenset({'research.control', 'control.commands.read'}))


def command():
    return dict(schema='unified.command.v1', command_id=str(uuid.uuid4()), actor_id='human-test', idempotency_key='intent-1',
                generation=GEN, aggregate_type='research', aggregate_id='main',
                expected_revision=0, action='SetResearchControl',
                payload={'mode': 'LAB_SIMULATION', 'state': 'RUNNING'})


def fixture():
    store = {'lab/test/commands/generation': (1, {'generation': GEN})}
    state = dict(index=10, offline=False, lost_response=False, transactions=0)
    session = str(uuid.UUID(int=4))

    def row(key):
        index, value = store[key]
        return dict(Key=key, ModifyIndex=index,
                    Value=base64.b64encode(json.dumps(value).encode()).decode(),
                    Session=session if key.endswith('/leader') else '')

    def handler(req):
        if state['offline']:
            return httpx.Response(503)
        path = req.url.path
        if path == '/v1/session/create':
            return httpx.Response(200, json={'ID': session})
        if path.startswith('/v1/kv/'):
            key = path[len('/v1/kv/'):]
            if req.method == 'PUT':
                store[key] = (10, json.loads(req.content))
                return httpx.Response(200, json=True)
            assert 'consistent' in req.url.params
            return httpx.Response(200, json=[row(key)]) if key in store else httpx.Response(404)
        assert path == '/v1/txn'
        ops = json.loads(req.content)
        pending = copy.deepcopy(store)
        for op in ops:
            op = op['KV']
            key, verb = op['Key'], op['Verb']
            current = store.get(key)
            valid = ((verb == 'check-session' and op['Session'] == session and key.endswith('/leader'))
                     or (verb == 'check-index' and (current[0] if current else 0) == op['Index'])
                     or verb == 'cas' and (current[0] if current else 0) == op['Index'])
            if not valid:
                return httpx.Response(409, json={'Errors': ['CAS']})
            if verb == 'cas':
                pending[key] = (state['index'] + 1, json.loads(base64.b64decode(op['Value'])))
        store.clear()
        store.update(pending)
        state['index'] += 1
        state['transactions'] += 1
        if state['lost_response']:
            state['lost_response'] = False
            raise httpx.ReadTimeout('lost committed response')
        return httpx.Response(200, json={'Results': []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    authority = ConsulSessionAuthority(ConsulConfig(endpoints=('http://127.0.0.1:8500',),
        namespace='lab/test', isolated_lab=True), client=client)
    return authority, client, store, state


def test_committed_research_state_retry_and_conflicts():
    async def scenario():
        authority, client, store, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            bridge = CoordinationCommands(authority, GEN, principal_provider=Provider())
            intent = command()
            first = await bridge.submit(lease, intent, 'verified-test-context')
            assert first['commit_status'] == 'COMMITTED'
            assert first['effect_status'] == 'PENDING_UNWIRED'
            assert first['revision'] == 1
            assert first['schema'] == 'unified.command-receipt.v1'
            assert first['consensus_modify_index'] == 11
            assert first['consensus_modify_index'] != first['leader_lock_index']
            assert await bridge.submit(lease, intent, 'verified-test-context') == first
            assert state['transactions'] == 1
            changed = copy.deepcopy(intent)
            changed['payload']['state'] = 'PAUSED'
            with pytest.raises(CommandDenied, match='IDEMPOTENCY_CONFLICT'):
                await bridge.submit(lease, changed, 'verified-test-context')
            stale = command()
            stale['idempotency_key'] = 'other'
            with pytest.raises(CommandDenied, match='REVISION_CONFLICT'):
                await bridge.submit(lease, stale, 'verified-test-context')
    asyncio.run(scenario())


def test_unknown_committed_response_reconciles_without_reexecution():
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            bridge = CoordinationCommands(authority, GEN, principal_provider=Provider())
            intent = command()
            state['lost_response'] = True
            result = await bridge.submit(lease, intent, 'verified-test-context')
            assert result['commit_status'] in ('UNKNOWN', 'COMMITTED')
            receipt = await bridge.get_command(intent['command_id'], 'verified-test-context')
            assert receipt['commit_status'] == 'COMMITTED'
            assert state['transactions'] == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('change', [dict(actor_id='SystemOwner'), dict(role='SystemOwner'),
    dict(expected_version=0), dict(expected_revision=True), dict(action='RealOrder'),
    dict(payload={'mode': 'REAL', 'state': 'RUNNING'}), dict(generation=str(uuid.uuid4())),
    dict(schema=1), dict(aggregate_type='research_control'),
    dict(payload={'mode': 'LAB', 'state': 'RUNNING'}), dict(expected_revision=2**53),
    dict(idempotency_key=':invalid')])
def test_untrusted_envelope_denied_without_mutation(change):
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            bridge = CoordinationCommands(authority, GEN, principal_provider=Provider())
            intent = command()
            intent.update(change)
            with pytest.raises((CommandDenied, ValueError)):
                await bridge.submit(lease, intent, 'verified-test-context')
            assert state['transactions'] == 0
    asyncio.run(scenario())


def test_no_auth_revocation_and_no_quorum_deny():
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            with pytest.raises(CommandDenied):
                await CoordinationCommands(authority, GEN).submit(lease, command(), None)
            provider = Provider()
            bridge = CoordinationCommands(authority, GEN, principal_provider=provider)
            intent = command()
            await bridge.submit(lease, intent, 'verified-test-context')
            provider.active = False
            with pytest.raises(CommandDenied):
                await bridge.get_command(intent['command_id'], 'verified-test-context')
            provider.active = True
            state['offline'] = True
            result = await bridge.submit(lease, command(), 'verified-test-context')
            assert result['commit_status'] == 'UNKNOWN'
            assert state['transactions'] == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('principal', [True, {'actor_id': 'owner'},
    CurrentPrincipal('human-test', True, 'HUMAN', frozenset({'research.control'})),
    CurrentPrincipal('human-test', 3, 'SERVICE', frozenset({'research.control'})),
    CurrentPrincipal('human-test', 3, 'HUMAN', frozenset())])
def test_structural_principal_rejects_forgery_and_machine_authority(principal):
    class BadProvider:
        async def require_current(self, *args):
            return principal
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            with pytest.raises(CommandDenied):
                await CoordinationCommands(authority, GEN, principal_provider=BadProvider()).submit(lease, command(), None)
            assert state['transactions'] == 0
    asyncio.run(scenario())


def test_current_authentication_rechecked_before_commit_and_replay():
    class RevokingProvider(Provider):
        calls = 0
        async def require_current(self, *args):
            self.calls += 1
            if self.calls > 1:
                raise CommandDenied('revoked')
            return await super().require_current(*args)
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            with pytest.raises(CommandDenied, match='revoked'):
                await CoordinationCommands(authority, GEN, principal_provider=RevokingProvider()).submit(
                    lease, command(), 'verified-test-context')
            assert state['transactions'] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('raw', [b'{"schema":1,"schema":2}', b'{"x":NaN}', b'{"x":1e999}',
    b'[' * 100 + b'0' + b']' * 100, b' ' * 32769, b'\xff', b'[]'],
    ids=['duplicate', 'nonfinite', 'overflow', 'depth', 'bytes', 'utf8', 'array'])
def test_raw_public_decoder_rejects_ambiguity_depth_and_bounds(raw):
    with pytest.raises(CommandDenied):
        parse_command(raw)


def test_raw_public_decoder_roundtrip():
    intent = command()
    assert parse_command(json.dumps(intent).encode()) == intent


def test_receipt_decoder_rejects_private_unknown_fields():
    unknown = dict(schema='unified.command-receipt.v1', command_id=str(uuid.uuid4()),
                   generation=GEN, commit_status='UNKNOWN', effect_status='UNKNOWN')
    assert validate_receipt(unknown) == unknown
    with pytest.raises(CommandDenied):
        validate_receipt(dict(unknown, actor_id='fabricated-owner'))


@pytest.mark.parametrize('corrupt', [dict(private_secret='must-not-leak'),
    dict(command_id=str(uuid.uuid4())), dict(commit_status='PASS'),
    dict(grant_revision=True)])
def test_stored_kv_corruption_never_discloses_arbitrary_receipt(corrupt):
    async def scenario():
        authority, client, store, _ = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            bridge = CoordinationCommands(authority, GEN, principal_provider=Provider())
            intent = command()
            await bridge.submit(lease, intent, 'verified-test-context')
            key = 'lab/test/commands/ids/' + intent['command_id']
            index, receipt = store[key]
            store[key] = (index, dict(receipt, **corrupt))
            with pytest.raises(CommandDenied):
                await bridge.get_command(intent['command_id'], 'verified-test-context')
    asyncio.run(scenario())


def test_own_receipt_read_needs_read_capability_not_mutation_capability():
    class Viewer:
        async def require_current(self, context, action, aggregate_id):
            assert action == 'ReadCommand'
            return CurrentPrincipal('human-test', 4, 'HUMAN', frozenset({'control.commands.read'}))
    async def scenario():
        authority, client, _, _ = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            intent = command()
            committed = await CoordinationCommands(authority, GEN, principal_provider=Provider()).submit(
                lease, intent, 'verified-test-context')
            viewer = CoordinationCommands(authority, GEN, principal_provider=Viewer())
            assert await viewer.get_command(intent['command_id'], None) == committed
    asyncio.run(scenario())


def test_postcommit_revocation_blocks_disclosure_without_undoing_committed_intent():
    class AfterCommitRevocation(Provider):
        calls = 0
        async def require_current(self, *args):
            self.calls += 1
            if self.calls == 3:
                raise CommandDenied('revoked after commit')
            return await super().require_current(*args)
    async def scenario():
        authority, client, _, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            intent = command()
            with pytest.raises(CommandDenied, match='revoked after commit'):
                await CoordinationCommands(authority, GEN, principal_provider=AfterCommitRevocation()).submit(
                    lease, intent, 'verified-test-context')
            assert state['transactions'] == 1
            reconciled = await CoordinationCommands(authority, GEN, principal_provider=Provider()).get_command(
                intent['command_id'], 'verified-test-context')
            assert reconciled['commit_status'] == 'COMMITTED'
    asyncio.run(scenario())


@pytest.mark.parametrize('audit_all', [False, True])
def test_cross_actor_receipt_requires_explicit_audit_capability(audit_all):
    class OtherViewer:
        async def require_current(self, context, action, aggregate_id):
            assert action == 'ReadCommand'
            caps = {'control.commands.read'} | ({'control.commands.audit_all'} if audit_all else set())
            return CurrentPrincipal('other-human', 4, 'HUMAN', frozenset(caps))
    async def scenario():
        authority, client, _, _ = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            intent = command()
            await CoordinationCommands(authority, GEN, principal_provider=Provider()).submit(
                lease, intent, 'verified-test-context')
            viewer = CoordinationCommands(authority, GEN, principal_provider=OtherViewer())
            if audit_all:
                assert (await viewer.get_command(intent['command_id'], None))['actor_id'] == 'human-test'
            else:
                with pytest.raises(CommandDenied, match='ownership'):
                    await viewer.get_command(intent['command_id'], None)
    asyncio.run(scenario())


@pytest.mark.parametrize('change', [dict(generation=str(uuid.uuid4())), dict(schema='legacy'),
    dict(private='hidden'), dict(command_id='invalid'), dict(payload={'mode':'REAL','state':'RUNNING'}),
    dict(revision=True)])
def test_existing_aggregate_corruption_denies_cas(change):
    async def scenario():
        authority, client, store, state = fixture()
        async with client:
            lease = await authority.acquire('LS5')
            aggregate = dict(schema='unified.research-control.v1', generation=GEN, revision=1,
                command_id=str(uuid.uuid4()), payload={'mode':'LAB_SIMULATION','state':'PAUSED'})
            aggregate.update(change)
            store['lab/test/commands/research_control/main'] = (7, aggregate)
            intent = command()
            intent['expected_revision'] = 1
            with pytest.raises(CommandDenied):
                await CoordinationCommands(authority, GEN, principal_provider=Provider()).submit(
                    lease, intent, 'verified-test-context')
            assert state['transactions'] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('raw', [b'{"revision":1,"revision":2}', b'{"x":NaN}',
    b'{"x":1e999}', b' ' * 32769, b'[' * 10 + b'0' + b']' * 10],
    ids=['duplicate','nonfinite','overflow','bytes','depth'])
def test_untrusted_storage_json_uses_strict_decoder(raw):
    from grid.coordination import CoordinationUnavailable
    async def scenario():
        authority, client, _, _ = fixture()
        async with client:
            async def request(*args, **kwargs):
                return [dict(Key='corrupt', ModifyIndex=2, Value=base64.b64encode(raw).decode())]
            authority._request = request
            with pytest.raises(CoordinationUnavailable):
                await CoordinationCommands(authority, GEN)._read('corrupt')
    asyncio.run(scenario())


def test_zero_grant_principal_cannot_submit_or_query_private_receipt():
    class ZeroGrant:
        async def require_current(self, *args):
            return CurrentPrincipal('human-test', 0, 'HUMAN',
                frozenset({'research.control','control.commands.read'}))
    async def scenario():
        authority, client, _, _ = fixture()
        async with client:
            async def forbidden_request(*args, **kwargs):
                raise AssertionError('invalid grant must not query authority')
            authority._request = forbidden_request
            bridge = CoordinationCommands(authority, GEN, principal_provider=ZeroGrant())
            with pytest.raises(CommandDenied):
                await bridge.submit(None, command(), None)
            with pytest.raises(CommandDenied):
                await bridge.get_command(str(uuid.uuid4()), None)
    asyncio.run(scenario())
