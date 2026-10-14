"""Prepared for opt-in disposable CI only; forbidden installed ports are guarded."""
import asyncio
import os
import pytest
import asyncpg
from grid import migrations as m
from grid.db import Database
from installer.windows_preflight import model_registry_index_ready
from _postgres_test_database import disposable_database

pytestmark=pytest.mark.skipif(os.environ.get('GRID_DISPOSABLE_POSTGRES_TESTS')!='1',
    reason='explicit disposable CI opt-in required; no installed PostgreSQL')


async def bootstrap47(pool,monkeypatch):
    db=Database();db.pool=pool
    await db.ensure_schema()
    with monkeypatch.context() as patch:
        patch.setattr(m,'MIGRATIONS',m.MIGRATIONS[:47])
        await m.apply_migrations(pool)
    assert await pool.fetchval('SELECT max(version) FROM schema_migrations')==47


async def indexes(pool):
    return dict((r['indexname'],r['indexdef']) for r in await pool.fetch(
        "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public'"))


def test48_index_is_only_expected_schema_change_and_replay_is_idempotent(monkeypatch):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool,monkeypatch)
            await pool.execute("INSERT INTO candles_1m(symbol,ts,close) VALUES('AUDIT48',now(),123)")
            before=await indexes(pool)
            columns=await pool.fetch("SELECT table_name,column_name,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
            await asyncio.gather(m.apply_migrations(pool),m.apply_migrations(pool))
            after=await indexes(pool)
            assert set(after)-set(before)=={'idx_model_registry_dataset_id'}
            assert all(after[n]==d for n,d in before.items())
            assert columns==await pool.fetch("SELECT table_name,column_name,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
            assert [r['version'] for r in await pool.fetch('SELECT version FROM schema_migrations ORDER BY version')]==list(range(1,49))
            assert await pool.fetchval("SELECT close FROM candles_1m WHERE symbol='AUDIT48'")==123
            async with pool.acquire() as c:
                async with c.transaction(readonly=True):assert await model_registry_index_ready(c)
            oid=await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid")
            await m.apply_migrations(pool)
            assert await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid")==oid
    asyncio.run(run())


@pytest.mark.parametrize('failure',['sql','ledger'])
def test48_transaction_rolls_back_index_and_version_before_retry(monkeypatch,failure):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool,monkeypatch)
            if failure=='sql':await pool.execute('ALTER TABLE model_registry RENAME COLUMN dataset_id TO missing_dataset_id')
            else:await pool.execute('ALTER TABLE schema_migrations ADD CONSTRAINT fail48 CHECK(version<>48)')
            with pytest.raises(asyncpg.PostgresError):await m.apply_migrations(pool)
            assert await pool.fetchval('SELECT max(version) FROM schema_migrations')==47
            assert await pool.fetchval("SELECT to_regclass('public.idx_model_registry_dataset_id')") is None
            if failure=='sql':await pool.execute('ALTER TABLE model_registry RENAME COLUMN missing_dataset_id TO dataset_id')
            else:await pool.execute('ALTER TABLE schema_migrations DROP CONSTRAINT fail48')
            await m.apply_migrations(pool)
            assert await pool.fetchval('SELECT max(version) FROM schema_migrations')==48
    asyncio.run(run())


def test48_history_name_and_future_version_fail_before_index_creation(monkeypatch):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool,monkeypatch)
            await pool.execute("UPDATE schema_migrations SET name='wrong' WHERE version=47")
            with pytest.raises(RuntimeError,match='name mismatch'):await m.apply_migrations(pool)
            await pool.execute("UPDATE schema_migrations SET name='collection_ownership_fencing' WHERE version=47")
            await pool.execute("INSERT INTO schema_migrations(version,name) VALUES(49,'unknown')")
            with pytest.raises(RuntimeError,match='unknown database schema version'):await m.apply_migrations(pool)
            assert await pool.fetchval("SELECT to_regclass('public.idx_model_registry_dataset_id')") is None
    asyncio.run(run())


def test48_same_name_wrong_index_is_not_readiness_evidence(monkeypatch):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool,monkeypatch)
            await pool.execute('CREATE INDEX idx_model_registry_dataset_id ON public.model_registry(model_family)')
            with pytest.raises(RuntimeError,match='index invariant'):
                await m.apply_migrations(pool)
            assert await pool.fetchval('SELECT max(version) FROM schema_migrations')==47
            async with pool.acquire() as c:
                async with c.transaction(readonly=True):assert not await model_registry_index_ready(c)
    asyncio.run(run())



def test48_correct_existing_index_keeps_identity_and_records_once(monkeypatch):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool,monkeypatch)
            await pool.execute('CREATE INDEX idx_model_registry_dataset_id ON public.model_registry(dataset_id)')
            oid=await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid")
            await m.apply_migrations(pool);await m.apply_migrations(pool)
            assert await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid")==oid
            assert await pool.fetchval('SELECT count(*) FROM schema_migrations WHERE version=48')==1
    asyncio.run(run())

@pytest.mark.parametrize('definition', [
    '(dataset_id DESC)', '(dataset_id ASC NULLS FIRST)', '(dataset_id DESC NULLS LAST)',
    '(dataset_id public.uuid_ops)', '(dataset_id) WITH (fillfactor=80)',
    '(dataset_id) WITH (deduplicate_items=off)', '(dataset_id) INCLUDE (model_family)',
    '(dataset_id) WHERE dataset_id IS NOT NULL', '((dataset_id::text))',
])
def test48_wrong_definition_preserves_index_and_ledger47(monkeypatch, definition):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool, monkeypatch)
            if 'public.uuid_ops' in definition:
                # Same name as built-in in another namespace; same operators are
                # intentional: namespace/OID identity must still reject it.
                await pool.execute('''CREATE OPERATOR CLASS public.uuid_ops FOR TYPE uuid USING btree AS
                    OPERATOR 1 < (uuid,uuid), OPERATOR 2 <= (uuid,uuid),
                    OPERATOR 3 = (uuid,uuid), OPERATOR 4 >= (uuid,uuid),
                    OPERATOR 5 > (uuid,uuid), FUNCTION 1 pg_catalog.uuid_cmp(uuid,uuid)''')
            await pool.execute('CREATE INDEX idx_model_registry_dataset_id ON public.model_registry '+definition)
            oid = await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid")
            before = await indexes(pool)
            for _ in range(2):
                with pytest.raises(RuntimeError, match='index invariant'):
                    await m.apply_migrations(pool)
                assert await pool.fetchval('SELECT max(version) FROM schema_migrations') == 47
            assert await indexes(pool) == before
            assert await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid") == oid
    asyncio.run(run())


def test48_collated_text_impostor_is_rejected(monkeypatch):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool, monkeypatch)
            # UUID is noncollatable: legitimate DDL cannot attach a collation to
            # it. Model a drifted schema via normal DDL, never edit pg_catalog.
            await pool.execute('ALTER TABLE public.model_registry DROP CONSTRAINT model_registry_dataset_id_fkey')
            await pool.execute('ALTER TABLE public.model_registry ALTER COLUMN dataset_id TYPE text USING dataset_id::text')
            await pool.execute('CREATE INDEX idx_model_registry_dataset_id ON public.model_registry(dataset_id COLLATE "C")')
            with pytest.raises(RuntimeError, match='index invariant'):
                await m.apply_migrations(pool)
            assert await pool.fetchval('SELECT max(version) FROM schema_migrations') == 47
    asyncio.run(run())


def test48_explicit_equivalent_defaults_are_accepted(monkeypatch):
    async def run():
        async with disposable_database() as pool:
            await bootstrap47(pool, monkeypatch)
            await pool.execute('CREATE INDEX idx_model_registry_dataset_id ON public.model_registry USING btree (dataset_id pg_catalog.uuid_ops ASC NULLS LAST)')
            oid = await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid")
            await m.apply_migrations(pool)
            await m.apply_migrations(pool)
            assert await pool.fetchval("SELECT 'public.idx_model_registry_dataset_id'::regclass::oid") == oid
            assert await pool.fetchval('SELECT count(*) FROM schema_migrations WHERE version=48') == 1
    asyncio.run(run())
