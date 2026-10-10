import asyncio
import os
import uuid
from types import SimpleNamespace

import asyncpg
import pytest
from fastapi import HTTPException

from grid import coordinator
from grid.control_plane import command_result, enqueue_command, ensure_control_schema


pytestmark = pytest.mark.skipif(not os.getenv('POSTGRES_DSN'), reason='isolated PostgreSQL DSN required')


async def isolated_commands(test):
    schema = 'command_audit_' + uuid.uuid4().hex
    connection = await asyncpg.connect(os.environ['POSTGRES_DSN'])
    pool = None
    try:
        await connection.execute(f'CREATE SCHEMA {schema}')
        pool = await asyncpg.create_pool(os.environ['POSTGRES_DSN'], min_size=1, max_size=2,
                                         server_settings={'search_path': schema})
        await ensure_control_schema(pool)
        await test(pool)
    finally:
        if pool is not None:
            await pool.close()
        await connection.execute(f'DROP SCHEMA {schema} CASCADE')
        await connection.close()


def test_atomic_ack_is_bound_to_the_command_owner():
    async def scenario(pool):
        cid = await enqueue_command(pool, 'worker-b', 'stop')
        assert await command_result(pool, cid, True, node_id='worker-a') is False
        assert await pool.fetchval('SELECT status FROM agent_commands WHERE id=$1', uuid.UUID(cid)) == 'queued'
        assert await command_result(pool, cid, True, node_id='worker-b') is True
        assert await pool.fetchval('SELECT status FROM agent_commands WHERE id=$1', uuid.UUID(cid)) == 'done'
    asyncio.run(isolated_commands(scenario))


@pytest.mark.parametrize('foreign', [True, False])
def test_worker_cannot_ack_foreign_or_missing_command(monkeypatch, foreign):
    async def scenario(pool):
        cid = await enqueue_command(pool, 'worker-b', 'resume') if foreign else str(uuid.uuid4())
        monkeypatch.setattr(coordinator, 'db', SimpleNamespace(pool=pool))
        reconciles = []

        async def authenticated(node_id, credential, fleet_token):
            assert (node_id, credential) == ('worker-a', 'credential-a')

        async def reconcile(pool):
            reconciles.append(True)

        monkeypatch.setattr(coordinator, 'node_auth', authenticated)
        monkeypatch.setattr(coordinator, 'reconcile_fleet_operation', reconcile)
        with pytest.raises(HTTPException) as error:
            await coordinator.post_command_result(cid, {'node_id':'worker-a', 'ok':True}, '', 'credential-a')
        assert error.value.status_code == 404
        assert reconciles == []
        if foreign:
            assert await pool.fetchval('SELECT status FROM agent_commands WHERE id=$1', uuid.UUID(cid)) == 'queued'
    asyncio.run(isolated_commands(scenario))


def test_owner_ack_reconciles_only_after_persistence(monkeypatch):
    async def scenario(pool):
        cid = await enqueue_command(pool, 'worker-a', 'stop')
        monkeypatch.setattr(coordinator, 'db', SimpleNamespace(pool=pool))

        async def authenticated(*args):
            pass

        async def reconcile(pool):
            assert await pool.fetchval('SELECT status FROM agent_commands WHERE id=$1', uuid.UUID(cid)) == 'done'

        monkeypatch.setattr(coordinator, 'node_auth', authenticated)
        monkeypatch.setattr(coordinator, 'reconcile_fleet_operation', reconcile)
        assert await coordinator.post_command_result(cid, {'node_id':'worker-a', 'ok':True}, '', 'credential-a') == {'ok':True}
    asyncio.run(isolated_commands(scenario))


def test_explicit_admin_ack_without_node_remains_supported(monkeypatch):
    async def scenario(pool):
        cid = await enqueue_command(pool, 'worker-b', 'stop')
        monkeypatch.setattr(coordinator, 'db', SimpleNamespace(pool=pool))
        monkeypatch.setattr(coordinator, 'auth', lambda token: token == 'admin-token' or pytest.fail('admin token required'))

        async def reconcile(pool):
            pass

        monkeypatch.setattr(coordinator, 'reconcile_fleet_operation', reconcile)
        assert await coordinator.post_command_result(cid, {'ok':True}, 'admin-token', '') == {'ok':True}
    asyncio.run(isolated_commands(scenario))
