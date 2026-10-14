"""Disposable random schema only. No real installation or external database writes."""
import asyncio
import os
import uuid
import asyncpg
import pytest
from grid.db import Database
from grid.migrations import apply_migrations
from grid.retention import ensure_retention_schema
from grid.runtime_gate import ensure_runtime_gate
from installer.windows_preflight import database_status

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='disposable CI database required')


def test_clean_bootstrap_retention_and_readonly_preflight_are_repeatable():
    async def run():
        schema='commission_'+uuid.uuid4().hex
        admin=await asyncpg.connect(os.environ['POSTGRES_DSN']);pool=None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            async def setup(c):await c.execute(f'SET search_path TO "{schema}"')
            pool=await asyncpg.create_pool(os.environ['POSTGRES_DSN'],min_size=1,max_size=2,setup=setup)
            db=Database();db.pool=pool
            await db.ensure_schema();await apply_migrations(pool)
            await ensure_runtime_gate(pool)
            async with pool.acquire() as c:
                assert (await database_status(c,await c.fetchval('SELECT current_database()')))['code']=='GRID_SCHEMA_INCOMPLETE'
            await ensure_retention_schema(pool)
            await pool.execute("INSERT INTO candles_1m(symbol,ts,close) VALUES('BTCUSDT',now(),123)")
            for _ in range(2):
                await db.ensure_schema();await apply_migrations(pool)
                await ensure_retention_schema(pool);await ensure_runtime_gate(pool)
                async with pool.acquire() as c:
                    result=await database_status(c,await c.fetchval('SELECT current_database()'))
                    assert result=={'status':'PASS','code':'DATABASE_READY','migration':47,'runtime_state':'INFRA_ONLY'}
            assert await pool.fetchval('SELECT count(*) FROM schema_migrations')==47
            assert await pool.fetchval('SELECT close FROM candles_1m')==123
            assert await pool.fetchval('SELECT count(*) FROM retention_runs')==0
            await pool.execute("UPDATE grid_runtime_state SET state='ACTIVE'")
            async with pool.acquire() as c:
                assert (await database_status(c,await c.fetchval('SELECT current_database()')))['code']=='RUNTIME_NOT_QUIESCENT'
            # A preflight/ensure pass must not silently reset an already-active fleet.
            await ensure_runtime_gate(pool)
            assert await pool.fetchval('SELECT state FROM grid_runtime_state')=='ACTIVE'
        finally:
            if pool:await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE');await admin.close()
    asyncio.run(run())
