import asyncio
import base64
import json
import httpx
import pytest


def run(coro):
    return asyncio.run(coro)


def test_production_requires_https_mtls_and_acl():
    from grid.coordination import ConsulConfig
    with pytest.raises(ValueError):
        ConsulConfig(endpoints=('http://127.0.0.1:8500',), namespace='grid/test')
    with pytest.raises(ValueError):
        ConsulConfig(endpoints=('https://consul.example:8501',), namespace='grid/test')


def fixture_authority():
    from grid.coordination import ConsulConfig, ConsulSessionAuthority
    state = {'session': '11111111-1111-1111-1111-111111111111', 'index': 17, 'value': None, 'txn': [], 'offline': False}
    def handler(request):
        if state['offline']:
            return httpx.Response(503, json={'error': 'no quorum'})
        if request.url.path == '/v1/session/create':
            return httpx.Response(200, json={'ID': state['session']})
        if request.url.path.startswith('/v1/session/renew/'):
            return httpx.Response(200, json=[{'ID': state['session']}])
        if request.url.path.startswith('/v1/session/destroy/'):
            return httpx.Response(200, json=True)
        if request.url.path == '/v1/txn':
            state['txn'].append(json.loads(request.content))
            return httpx.Response(200, json={'Results': []})
        if request.method == 'PUT':
            state['value'] = base64.b64encode(request.content).decode()
            return httpx.Response(200, json=True)
        assert 'consistent' in request.url.params
        return httpx.Response(200, json=[{'Key': 'lab-grid/test/leader', 'Session': state['session'], 'ModifyIndex': state['index'], 'Value': state['value']}])
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = ConsulConfig(endpoints=('http://127.0.0.1:8500',), namespace='lab-grid/test', isolated_lab=True)
    return ConsulSessionAuthority(config, client=client), state, client


def test_session_owner_and_raft_index_bind_protected_write():
    async def scenario():
        authority, state, client = fixture_authority()
        async with client:
            lease = await authority.acquire('node-a')
            assert (lease.owner, lease.token) == ('node-a', 17)
            assert await authority.validate(lease) is True
            await authority.write_control(lease, 'placements', {'job': 'node-a'})
            ops = state['txn'][0]
            assert ops[0]['KV'] == {'Verb': 'check-session', 'Key': 'lab-grid/test/leader', 'Session': lease.session_id}
            assert ops[1]['KV'] == {'Verb': 'check-index', 'Key': 'lab-grid/test/leader', 'Index': 17}
            value = json.loads(base64.b64decode(ops[2]['KV']['Value']))
            assert value['token'] == 17 and value['owner'] == 'node-a'
    run(scenario())


def test_stale_token_or_session_loss_never_publishes_control_state():
    async def scenario():
        from grid.coordination import CoordinationLost
        authority, state, client = fixture_authority()
        async with client:
            lease = await authority.acquire('node-a')
            state['index'] = 18
            assert await authority.validate(lease) is False
            with pytest.raises(CoordinationLost):
                await authority.write_control(lease, 'placements', {'job': 'stale'})
            assert state['txn'] == []
            state['offline'] = True
            assert await authority.renew(lease) is False
            assert await authority.validate(lease) is False
    run(scenario())


def test_floating_leader_does_not_fall_back_when_dcs_is_unavailable():
    async def scenario():
        from grid.floating_leader import FloatingLeader
        from grid.coordination import CoordinationUnavailable
        class Authority:
            async def acquire(self, owner):
                raise CoordinationUnavailable('no quorum')
        class Pool:
            def acquire(self):
                raise AssertionError('PostgreSQL-only fallback forbidden')
        leader = FloatingLeader(Pool(), 'node-a', coordination=Authority())
        with pytest.raises(CoordinationUnavailable):
            await leader.campaign()
        assert not leader.is_leader and leader.epoch is None
    run(scenario())


def test_dcs_loss_stops_existing_leader_before_pg_renewal():
    async def scenario():
        from grid.floating_leader import FloatingLeader
        class Authority:
            async def renew(self, lease): return False
        class Pool:
            async def execute(self, *args): raise AssertionError('must not extend PG lease after DCS loss')
        leader = FloatingLeader(Pool(), 'node-a', coordination=Authority())
        leader.is_leader = True
        leader.epoch = 42
        leader.coordination_lease = object()
        assert await leader.renew() is False
        assert leader.is_leader is False and leader.epoch is None
    run(scenario())


def test_unreachable_first_endpoint_does_not_hide_healthy_quorum_endpoint():
    async def scenario():
        from grid.coordination import ConsulConfig, ConsulSessionAuthority
        async def handler(request):
            if request.url.host == '127.0.0.1':
                await asyncio.sleep(.2)
            return httpx.Response(200, json=[{'Value': base64.b64encode(b'{"payload":"quorum-data"}').decode()}])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            config = ConsulConfig(endpoints=('http://127.0.0.1:8500', 'http://127.0.0.2:8500'),
                                  namespace='lab-grid/endpoint-failover', isolated_lab=True, request_timeout=.1)
            authority = ConsulSessionAuthority(config, client=client)
            assert await authority.read_control('probe') == {'payload': 'quorum-data'}
    run(scenario())


def test_rollout_guard_binds_pg_epoch_to_current_consul_owner():
    async def scenario():
        from grid.coordination import floating_leader_guard, CoordinationLost
        from grid.floating_leader import FloatingLeader
        authority, state, client = fixture_authority()
        class Pool:
            live = True
            async def fetchval(self, query, owner, epoch):
                assert owner == 'node-a' and epoch == 42
                return self.live
        async with client:
            lease = await authority.acquire('node-a')
            pool = Pool()
            leader = FloatingLeader(pool, 'node-a', coordination=authority)
            leader.is_leader = True
            leader.epoch = 42
            leader.coordination_lease = lease
            guard = floating_leader_guard(leader)
            assert await guard() == {'owner': 'node-a', 'epoch': 42}
            pool.live = False
            with pytest.raises(CoordinationLost): await guard()
            pool.live = True
            state['index'] += 1
            with pytest.raises(CoordinationLost): await guard()
    run(scenario())


def test_lost_dcs_after_pg_commit_does_not_expose_leadership():
    async def scenario():
        from grid.floating_leader import FloatingLeader
        from grid.coordination import ConsulLease
        lease = ConsulLease('node-a', '11111111-1111-1111-1111-111111111111', 17)
        released = []
        class Authority:
            async def acquire(self, owner): return lease
            async def validate(self, value): return False
            async def release(self, value): released.append(value)
        class Pool:
            async def execute(self, sql, owner, epoch):
                assert owner == 'node-a' and epoch == 42
                return 'UPDATE 1'
        leader = FloatingLeader(Pool(), 'node-a', coordination=Authority())
        async def committed():
            leader.is_leader = True; leader.epoch = 42
            return True
        leader._campaign_pg = committed
        assert await leader.campaign() is False
        assert not leader.is_leader and leader.epoch is None and leader.coordination_lease is None
        assert released == [lease]
    run(scenario())


def test_read_finishing_after_local_ttl_cannot_validate_lease():
    async def scenario():
        authority, state, client = fixture_authority()
        now = [0.0]
        authority.clock = lambda: now[0]
        async with client:
            lease = await authority.acquire('node-a')
            original_read = authority._read_lock
            async def delayed_read():
                row = await original_read()
                now[0] = authority.config.ttl_seconds + 1
                return row
            authority._read_lock = delayed_read
            assert await authority.validate(lease) is False
    run(scenario())


def test_foreign_or_reconstructed_lease_does_not_gain_observer_authority():
    async def scenario():
        from grid.coordination import ConsulSessionAuthority
        authority, state, client = fixture_authority()
        async with client:
            lease = await authority.acquire('node-a')
            observer = ConsulSessionAuthority(authority.config, client=client)
            assert await observer.validate(lease) is False
    run(scenario())
