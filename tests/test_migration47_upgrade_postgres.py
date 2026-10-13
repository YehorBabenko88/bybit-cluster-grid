"""Actual 46→47 SQL and fail-closed old catalogue; disposable CI schema only."""
import asyncio
import os
import uuid
import asyncpg
import pytest
from grid.db import Database
from grid import migrations
from grid.collection_ownership import grant_assignments,wal_envelope
from grid.fenced_ingest import ingest_owned

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='disposable CI database only')


def test_upgrade47_keeps_data_and_old_catalogue_refuses_without_downgrade(monkeypatch):
    async def run():
        schema='upgrade47_'+uuid.uuid4().hex
        admin=await asyncpg.connect(os.environ['POSTGRES_DSN']);pool=None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            async def setup(c):await c.execute(f'SET search_path TO "{schema}"')
            pool=await asyncpg.create_pool(os.environ['POSTGRES_DSN'],min_size=2,max_size=4,setup=setup)
            db=Database();db.pool=pool;await db.ensure_schema()
            current=migrations.MIGRATIONS
            old=[m for m in current if m[0]<47]
            monkeypatch.setattr(migrations,'MIGRATIONS',old)
            await migrations.apply_migrations(pool)
            assert await pool.fetchval('SELECT max(version) FROM schema_migrations')==46
            await pool.execute("""INSERT INTO candles_1m(symbol,ts,close,quality_status)
              VALUES('BTCUSDT',to_timestamp(1700000000),100,'GOOD')""")
            monkeypatch.setattr(migrations,'MIGRATIONS',current)
            await asyncio.gather(migrations.apply_migrations(pool),migrations.apply_migrations(pool))
            assert await pool.fetchval('SELECT count(*) FROM schema_migrations WHERE version=47')==1
            await grant_assignments(pool,'node',str(uuid.uuid4()),['BTCUSDT'])
            row=wal_envelope({'symbol':'BTCUSDT','value':1})
            async def forbidden(*args):raise AssertionError('legacy replay became live')
            assert (await ingest_owned(pool,'node','event',row,forbidden))['disposition']=='QUARANTINED'
            monkeypatch.setattr(migrations,'MIGRATIONS',old)
            with pytest.raises(RuntimeError,match='unknown database schema version 47'):
                await migrations.apply_migrations(pool)
            assert await pool.fetchval('SELECT count(*) FROM collection_ingest_receipts')==1
            assert await pool.fetchval("SELECT close FROM candles_1m WHERE symbol='BTCUSDT'")==100
            assert await pool.fetchval('SELECT max(version) FROM schema_migrations')==47
            monkeypatch.setattr(migrations,'MIGRATIONS',current)
            await migrations.apply_migrations(pool)
            assert await pool.fetchval('SELECT count(*) FROM collection_ingest_receipts')==1
        finally:
            if pool:await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(run())
