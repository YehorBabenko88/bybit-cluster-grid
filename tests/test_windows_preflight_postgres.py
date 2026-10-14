"""Disposable fresh public database only. No installation/working database writes."""
import asyncio
import os
import pytest
from grid.db import Database
from grid import migrations
from grid.retention import ensure_retention_schema
from grid.runtime_gate import ensure_runtime_gate
from installer.windows_preflight import database_status
from _postgres_test_database import disposable_database

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='disposable CI database required')


def test_clean_bootstrap_retention_and_readonly_preflight_are_repeatable(monkeypatch):
    async def run():
        async with disposable_database() as pool:
            db=Database();db.pool=pool
            current=migrations.MIGRATIONS
            monkeypatch.setattr(migrations,'MIGRATIONS',current[:47])
            await db.ensure_schema();await migrations.apply_migrations(pool)
            await ensure_runtime_gate(pool)
            async with pool.acquire() as c:
                assert (await database_status(c,await c.fetchval('SELECT current_database()')))['code']=='GRID_SCHEMA_INCOMPLETE'
            await ensure_retention_schema(pool)
            # Existing legacy47 approval is preserved, never widened to48.
            async with pool.acquire() as c:
                result=await database_status(c,await c.fetchval('SELECT current_database()'),legacy_rollback=True)
                assert result['code']=='LEGACY_SCHEMA47_READY_OFFLINE_ONLY'
                await c.execute("INSERT INTO service_leases(service_key,owner,lease_until) VALUES('legacy-test','fixture',now()+interval '1 minute')")
                assert (await database_status(c,await c.fetchval('SELECT current_database()'),legacy_rollback=True))['code']=='LEGACY_RUNTIME_LEASE_ACTIVE'
                await c.execute("UPDATE service_leases SET lease_until=now()-interval '1 second' WHERE service_key='legacy-test'")
                await c.execute("UPDATE schema_migrations SET name='incompatible' WHERE version=47")
                assert (await database_status(c,await c.fetchval('SELECT current_database()'),legacy_rollback=True))['code']=='MIGRATION_CATALOGUE_MISMATCH'
                await c.execute("UPDATE schema_migrations SET name='collection_ownership_fencing' WHERE version=47")
            monkeypatch.setattr(migrations,'MIGRATIONS',current)
            await migrations.apply_migrations(pool)
            await pool.execute("INSERT INTO candles_1m(symbol,ts,close) VALUES('BTCUSDT',now(),123)")
            for _ in range(2):
                await db.ensure_schema();await migrations.apply_migrations(pool)
                await ensure_retention_schema(pool);await ensure_runtime_gate(pool)
                async with pool.acquire() as c:
                    result=await database_status(c,await c.fetchval('SELECT current_database()'))
                    assert result=={'status':'PASS','code':'DATABASE_READY','migration':48,'runtime_state':'INFRA_ONLY'}
                    assert (await database_status(c,await c.fetchval('SELECT current_database()'),legacy_rollback=True))['code']=='MIGRATION_CATALOGUE_MISMATCH'
            assert await pool.fetchval('SELECT count(*) FROM schema_migrations')==48
            assert await pool.fetchval('SELECT close FROM candles_1m')==123
            assert await pool.fetchval('SELECT count(*) FROM retention_runs')==0
            await pool.execute("UPDATE grid_runtime_state SET state='ACTIVE'")
            async with pool.acquire() as c:
                assert (await database_status(c,await c.fetchval('SELECT current_database()')))['code']=='RUNTIME_NOT_QUIESCENT'
            await ensure_runtime_gate(pool)
            assert await pool.fetchval('SELECT state FROM grid_runtime_state')=='ACTIVE'
    asyncio.run(run())
