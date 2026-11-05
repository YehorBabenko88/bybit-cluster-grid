"""PG18 qualification is restricted to the reviewed hosted disposable service.

No ambient/local PostgreSQL DSN is accepted. Every connection checkout selects
one generated private schema; the public object inventory must remain unchanged.
"""
import asyncio
import json
import os
import re
import uuid

import asyncpg
import pytest

from grid.control_state import put_control_state


def _disposable_dsn(environ):
    fixed = 'postgresql://grid:grid@127.0.0.1:5432/grid'
    expected = {
        'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
        'GITHUB_REPOSITORY': 'YehorBabenko88/bybit-cluster-grid',
        'GITHUB_JOB': 'linux-postgres18', 'HISTORY_DISPOSABLE_DSN': fixed,
        'MISSION3_TEST_DATABASE_URL': fixed,
    }
    if any(environ.get(key) != value for key, value in expected.items()):
        raise ValueError('DISPOSABLE_PG_JOB_REQUIRED')
    return fixed


def _private_schema(value):
    if type(value) is not str or re.fullmatch(r'control_fence_test_[a-f0-9]{32}', value) is None:
        raise ValueError('PRIVATE_SCHEMA_REQUIRED')
    return value


async def _public_objects(conn):
    return [tuple(row) for row in await conn.fetch('''SELECT c.oid::bigint,c.relname,c.relkind
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' ORDER BY c.oid''')]


def _hosted_environment():
    fixed = 'postgresql://grid:grid@127.0.0.1:5432/grid'
    return {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
            'GITHUB_REPOSITORY': 'YehorBabenko88/bybit-cluster-grid',
            'GITHUB_JOB': 'linux-postgres18', 'HISTORY_DISPOSABLE_DSN': fixed,
            'MISSION3_TEST_DATABASE_URL': fixed}


@pytest.mark.parametrize('key', list(_hosted_environment()))
def test_hosted_guard_rejects_each_missing_or_changed_context_before_connect(monkeypatch, key):
    async def forbidden(*args, **kwargs):
        raise AssertionError('database connection attempted before guard')
    monkeypatch.setattr(asyncpg, 'connect', forbidden)
    monkeypatch.setattr(asyncpg, 'create_pool', forbidden)
    environment = _hosted_environment()
    for value in (None, 'unreviewed'):
        changed = dict(environment)
        if value is None:
            del changed[key]
        else:
            changed[key] = value
        with pytest.raises(ValueError, match='DISPOSABLE_PG_JOB_REQUIRED'):
            asyncio.run(_scenario(changed))
    assert _disposable_dsn(environment) == environment['HISTORY_DISPOSABLE_DSN']


def test_private_schema_guard_rejects_shared_or_unvalidated_targets():
    for name in ('public', 'control_fence_test_', 'control_fence_test_'+'a'*32+';DROP SCHEMA public', None):
        with pytest.raises(ValueError, match='PRIVATE_SCHEMA_REQUIRED'):
            _private_schema(name)


async def _scenario(environ):
    # Guard executes before even opening an admin connection.
    dsn = _disposable_dsn(environ)
    schema = _private_schema('control_fence_test_' + uuid.uuid4().hex)
    admin = await asyncpg.connect(dsn, server_settings={'search_path': 'pg_catalog'})
    pool = None
    created = False
    tasks = []
    public_before = None
    try:
        version = int(await admin.fetchval('SHOW server_version_num'))
        assert 180000 <= version < 190000, 'POSTGRES18_REQUIRED'
        public_before = await _public_objects(admin)
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        created = True
        # Exact production shapes: migration12 service lease and migration16 state.
        await admin.execute(f'''CREATE TABLE "{schema}".service_leases(
            service_key text PRIMARY KEY,owner text NOT NULL,lease_until timestamptz NOT NULL,
            heartbeat_at timestamptz NOT NULL DEFAULT now(),metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb)''')
        await admin.execute(f'''CREATE TABLE "{schema}".replicated_control_state(
            state_key text PRIMARY KEY,value jsonb NOT NULL,version bigint NOT NULL DEFAULT 1,
            updated_at timestamptz NOT NULL DEFAULT now(),updated_by text NOT NULL)''')

        async def setup(conn):
            # setup runs after every asyncpg RESET ALL / checkout, not just once.
            await conn.execute(f'SET search_path TO "{schema}"')
            assert await conn.fetchval('SELECT current_schema()') == schema
            assert await conn.fetchval('SELECT current_schemas(false)') == [schema]

        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3,
                                        setup=setup, server_settings={'search_path': 'pg_catalog'})
        for _ in range(4):
            async with pool.acquire() as conn:
                assert await conn.fetchval('SELECT current_schema()') == schema

        async def lease(owner, epoch, seconds=120):
            await pool.execute('''INSERT INTO service_leases(service_key,owner,lease_until,metadata)
                VALUES('control-plane-leader',$1,clock_timestamp()+($2::float8*interval '1 second'),$3::jsonb)
                ON CONFLICT(service_key) DO UPDATE SET owner=EXCLUDED.owner,
                lease_until=EXCLUDED.lease_until,metadata=EXCLUDED.metadata''',
                owner, seconds, json.dumps({'epoch': epoch}))

        def fence(owner='one', epoch=7):
            return {'service_key': 'control-plane-leader', 'owner': owner, 'epoch': epoch}

        await lease('one', 7)
        for binding in (fence('two', 7), fence('one', 6)):
            assert await put_control_state(pool, 'delivery', {'delivered': False}, binding['owner'],
                                           expected_version=0, service_fence=binding) is None
        assert await pool.fetchval('SELECT count(*) FROM replicated_control_state') == 0
        await lease('one', 7, seconds=-1)
        assert await put_control_state(pool, 'delivery', {'delivered': False}, 'one',
                                       expected_version=0, service_fence=fence()) is None
        await lease('one', 7)
        assert await put_control_state(pool, 'delivery', {'delivered': False}, 'one',
                                       expected_version=0, service_fence=fence()) == 1
        assert await put_control_state(pool, 'delivery', {'delivered': True}, 'one',
                                       expected_version=0, service_fence=fence()) is None
        for binding in (fence('two', 7), fence('one', 6)):
            assert await put_control_state(pool, 'delivery', {'delivered': True}, binding['owner'],
                                           expected_version=1, service_fence=binding) is None
        await lease('one', 7, seconds=-1)
        assert await put_control_state(pool, 'delivery', {'delivered': True}, 'one',
                                       expected_version=1, service_fence=fence()) is None
        await lease('one', 7)
        assert await put_control_state(pool, 'delivery', {'delivered': True}, 'one',
                                       expected_version=99, service_fence=fence()) is None
        assert await put_control_state(pool, 'delivery', {'delivered': False, 'sequence': 1}, 'one',
                                       expected_version=1, service_fence=fence()) == 2

        # A held, uncommitted epoch replacement must block the old leader's
        # SELECT FOR SHARE, then reject its delivered-style acknowledgement.
        entered = asyncio.Event()
        async with pool.acquire() as revoker:
            async with revoker.transaction():
                await revoker.execute('''UPDATE service_leases SET owner='two',metadata='{"epoch":8}'::jsonb,
                    lease_until=clock_timestamp()+interval '120 seconds'
                    WHERE service_key='control-plane-leader' ''')
                async def stale_ack():
                    async with pool.acquire() as conn:
                        assert await conn.fetchval('SELECT current_schema()') == schema
                        entered.set()
                        return await put_control_state(conn, 'delivery', {'delivered': True}, 'one',
                                                       expected_version=2, service_fence=fence())
                stale = asyncio.create_task(stale_ack())
                tasks.append(stale)
                await asyncio.wait_for(entered.wait(), 5)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(stale), 0.2)
                assert await revoker.fetchval("SELECT version FROM replicated_control_state WHERE state_key='delivery'") == 2
        assert await asyncio.wait_for(stale, 5) is None
        row = await pool.fetchrow("SELECT value,version FROM replicated_control_state WHERE state_key='delivery'")
        value = json.loads(row['value']) if isinstance(row['value'], str) else row['value']
        assert value == {'delivered': False, 'sequence': 1} and row['version'] == 2
        assert await put_control_state(pool, 'delivery', {'delivered': True}, 'two',
                                       expected_version=2, service_fence=fence('two', 8)) == 3

        # The reverse ordering serializes too: the valid writer's service share
        # lock remains held until its short transaction commits.
        revocation_entered = asyncio.Event()
        async with pool.acquire() as writer:
            async with writer.transaction():
                assert await put_control_state(writer, 'delivery', {'delivered': True, 'sequence': 2}, 'two',
                                               expected_version=3, service_fence=fence('two', 8)) == 4
                async def replace_after_ack():
                    async with pool.acquire() as conn:
                        revocation_entered.set()
                        await conn.execute('''UPDATE service_leases SET owner='three',metadata='{"epoch":9}'::jsonb
                            WHERE service_key='control-plane-leader' ''')
                replacement = asyncio.create_task(replace_after_ack())
                tasks.append(replacement)
                await asyncio.wait_for(revocation_entered.wait(), 5)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(replacement), 0.2)
        await asyncio.wait_for(replacement, 5)
        assert await put_control_state(pool, 'delivery', {'delivered': False}, 'two',
                                       expected_version=4, service_fence=fence('two', 8)) is None

        # Existing callers retain their original unfenced insert/CAS behavior.
        await lease('three', 9, seconds=-1)
        assert await put_control_state(pool, 'legacy', {'value': 1}, 'legacy-node') == 1
        assert await put_control_state(pool, 'legacy', {'value': 2}, 'legacy-node', expected_version=1) == 2
        assert await put_control_state(pool, 'legacy', {'value': 3}, 'legacy-node', expected_version=1) is None
        for _ in range(4):
            async with pool.acquire() as conn:
                assert await conn.fetchval('SELECT current_schema()') == schema
        assert await _public_objects(admin) == public_before
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if pool:
                await pool.close()
            if created:
                target = _private_schema(schema)
                await admin.execute(f'DROP SCHEMA "{target}" CASCADE')
            if public_before is not None:
                assert await _public_objects(admin) == public_before, 'PUBLIC_OBJECT_INVENTORY_CHANGED'
        finally:
            await admin.close()


@pytest.mark.skipif(not os.environ.get('HISTORY_DISPOSABLE_DSN'),
                    reason='hosted disposable PostgreSQL18 unavailable; local PG NOT_RUN')
def test_real_postgres18_service_fence_initialization_cas_and_lease_serialization():
    asyncio.run(_scenario(os.environ))
