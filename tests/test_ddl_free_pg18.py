"""Actual PostgreSQL 18 tests; only the attested GitHub-hosted provider is allowed."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest
from _pg18_database import database, grant_runtime
from grid import migrations
from grid.schema_contract import SchemaBlocked, catalog_digest, verify_runtime_schema
from grid.schema_preparation import prepare_schema

pytestmark=pytest.mark.skipif(os.environ.get('GRID_PG18_TESTS')!='1',reason='attested disposable PG18 CI only')


def test_fresh_48_and_idempotent_preparation():
    async def run():
        async with database(False) as (p,r,*_):
            assert await prepare_schema(p['owner'])=='PREPARED'
            assert await p['owner'].fetchval('SELECT count(*) FROM schema_migrations')==48
            assert await prepare_schema(p['owner'])=='ALREADY_PREPARED'
            await grant_runtime(p['owner'],r)
            await verify_runtime_schema(p['app'])
    asyncio.run(run())


def test_concurrent_preparation_is_serialized():
    async def run():
        async with database(False) as (p,*_):
            assert sorted(await asyncio.gather(prepare_schema(p['owner']),prepare_schema(p['owner'])))==['ALREADY_PREPARED','PREPARED']
    asyncio.run(run())


@pytest.mark.parametrize('sql',[
    'CREATE TABLE public.forbidden(id int)',
    'CREATE TEMP TABLE forbidden(id int)',
    'CREATE SCHEMA forbidden',
    'ALTER TABLE public.candles_1m ADD COLUMN forbidden int',
    'DROP TABLE public.candles_1m',
    'CREATE INDEX forbidden ON public.candles_1m(symbol)',
    'UPDATE public.schema_migrations SET name=name',
    'DELETE FROM public.grid_schema_contract',
],ids=['create-table','temp','schema','alter','drop','index','registry-write','seal-write'])
def test_app_has_no_ddl_or_metadata_write(sql):
    async def run():
        async with database() as (p,*_):
            await verify_runtime_schema(p['app'])
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await p['app'].execute(sql)
    asyncio.run(run())


def test_app_dml_and_readonly_allowlist_even_with_readonly_off():
    async def run():
        async with database() as (p,*_):
            await p['app'].execute("INSERT INTO candles_1m(symbol,ts,close) VALUES('SYNTHETIC',now(),1)")
            assert await p['ro'].fetchval('SELECT count(*) FROM candles_1m')==1
            for sql in ('UPDATE candles_1m SET close=2','SELECT * FROM agent_credentials','CREATE TABLE nope(id int)'):
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await p['ro'].execute(sql)
    asyncio.run(run())


@pytest.mark.parametrize('sql',[
    "UPDATE schema_migrations SET name='wrong' WHERE version=48",
    'DELETE FROM schema_migrations WHERE version=47',
    "INSERT INTO schema_migrations(version,name) VALUES(49,'unknown')",
    'ALTER TABLE fleet_operations DROP COLUMN details',
    'DROP INDEX idx_model_registry_dataset_id',
    "UPDATE grid_schema_contract SET source_sha256='corrupt'",
    'DELETE FROM grid_runtime_state',
],ids=['name','partial','unknown','column','index48','seal','gate'])
def test_registry_and_structure_drift_are_fatal(sql):
    async def run():
        async with database() as (p,*_):
            await p['owner'].execute(sql)
            with pytest.raises(SchemaBlocked):
                await verify_runtime_schema(p['app'])
            with pytest.raises(SchemaBlocked):
                await prepare_schema(p['owner'])
    asyncio.run(run())


def test_schema_failure_rolls_back_everything_and_can_retry(monkeypatch):
    async def run():
        async with database(False) as (p,*_):
            bad=list(migrations.MIGRATIONS)
            v,n,sql=bad[47]
            bad[47]=(v,n,[*sql,'SELECT 1/0'])
            with monkeypatch.context() as patch:
                patch.setattr(migrations,'MIGRATIONS',bad)
                with pytest.raises(asyncpg.DivisionByZeroError):
                    await prepare_schema(p['owner'])
            assert await p['owner'].fetchval("SELECT to_regclass('public.schema_migrations')") is None
            assert await prepare_schema(p['owner'])=='PREPARED'
    asyncio.run(run())


def test_cancelled_preparation_rolls_back_and_releases_lock(monkeypatch):
    async def run():
        async with database(False) as (p,*_):
            entered=asyncio.Event()
            async def pause(_):
                entered.set()
                await asyncio.Event().wait()
            import grid.retention as retention
            with monkeypatch.context() as patch:
                patch.setattr(retention,'ensure_retention_schema',pause)
                task=asyncio.create_task(prepare_schema(p['owner']))
                await asyncio.wait_for(entered.wait(),10)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):await task
            assert await p['owner'].fetchval("SELECT to_regclass('public.schema_migrations')") is None
            assert await asyncio.wait_for(prepare_schema(p['owner']),15)=='PREPARED'
    asyncio.run(run())


def test_unsealed_existing_schema_is_not_adopted():
    async def run():
        async with database(False) as (p,*_):
            await p['owner'].execute('CREATE TYPE public.unexpected AS ENUM(\'x\')')
            with pytest.raises(SchemaBlocked,match='UNSEALED'):
                await prepare_schema(p['owner'])
    asyncio.run(run())


def test_unsafe_role_and_metadata_privileges_fail_closed():
    async def run():
        async with database() as (p,r,*_):
            with pytest.raises(SchemaBlocked,match='DDL_AUTHORITY'):
                await verify_runtime_schema(p['owner'])
            await p['owner'].execute(f'GRANT UPDATE(source_sha256) ON grid_schema_contract TO "{r["app"]}"')
            with pytest.raises(SchemaBlocked,match='METADATA_WRITABLE'):
                await verify_runtime_schema(p['app'])
    asyncio.run(run())


def test_shadow_search_path_cannot_redirect_runtime(monkeypatch):
    async def run():
        from grid.db import Database
        from grid.config import settings
        async with database() as (p,r,options,name,admin):
            await p['owner'].execute('CREATE SCHEMA shadow')
            await p['owner'].execute('CREATE TABLE shadow.candles_1m(symbol text)')
            await p['owner'].execute(f'GRANT USAGE ON SCHEMA shadow TO "{r["app"]}"')
            await p['owner'].execute(f'GRANT SELECT,INSERT ON shadow.candles_1m TO "{r["app"]}"')
            await admin.execute(f'ALTER ROLE "{r["app"]}" SET search_path=shadow,public')
            # Credential is inherited in protected CI environment, never argv/DSN artifacts.
            dsn=f'postgresql://{r["app"]}@127.0.0.1:{options["port"]}/{name}'
            monkeypatch.setenv('PGPASSWORD',os.environ['GRID_PG18_PASSWORD'])
            monkeypatch.setattr(settings,'postgres_dsn',dsn)
            db=Database()
            await db.connect()
            try:
                await verify_runtime_schema(db.pool)
                for _ in range(2):
                    assert await db.pool.fetchval('SHOW search_path')=='pg_catalog, public'
                    assert await db.pool.fetchval("SELECT 'candles_1m'::regclass::oid='public.candles_1m'::regclass::oid")
            finally:await db.close()
    asyncio.run(run())


def test_legacy_import_is_dml_only_and_conflicts_abort():
    async def run():
        from grid.legacy_bootstrap_import import _merge_batch
        async with database() as (p,*_):
            row=('SYNTHETIC',datetime(2026,1,1,tzinfo=timezone.utc),*[Decimal(1)]*6)
            async with p['app'].acquire() as c:
                async with c.transaction():assert await _merge_batch(c,[row])==1
                async with c.transaction():assert await _merge_batch(c,[row])==0
                changed=(*row[:2],Decimal(2),*row[3:])
                with pytest.raises(RuntimeError,match='OHLCV_DATA_CONFLICT'):
                    async with c.transaction():await _merge_batch(c,[changed])
            assert await p['app'].fetchval('SELECT open FROM ohlcv_1m')==Decimal(1)
    asyncio.run(run())


def test_real_coordinator_start_stop_restart_under_app_role(monkeypatch):
    async def run():
        from grid import coordinator as co
        from grid import derived_pipeline
        from grid.config import settings
        async with database() as (p,r,options,name,admin):
            dsn=f'postgresql://{r["app"]}@127.0.0.1:{options["port"]}/{name}'
            monkeypatch.setenv('PGPASSWORD',os.environ['GRID_PG18_PASSWORD'])
            monkeypatch.setattr(settings,'postgres_dsn',dsn)
            monkeypatch.setattr(settings,'retention_enabled',False)
            monkeypatch.setattr(co,'bootstrap_logging',lambda:None)
            # Only compute/scheduled maintenance/Telegram are isolated. Actual
            # Storage/WAL, features, scientific initialization, derived pipeline,
            # startup verification, election and fencing use disposable fixtures.
            class External:
                def __init__(self,*args):self.feature_builder=self
                async def start(self,*args):pass
                async def close(self):pass
                async def run(self):await asyncio.Event().wait()
                def stop(self):pass
            monkeypatch.setattr(co,'MLOrchestratorService',External)
            async def quiet(*args):await asyncio.Event().wait()
            for name_ in ('telegram_loop','retention_scheduler','maintenance_scheduler'):
                monkeypatch.setattr(co,name_,quiet)
            async with p['owner'].acquire() as c:before=await catalog_digest(c)
            for _ in range(2):
                await co.startup()
                try:
                    for _ in range(100):
                        if co.control_runtime.ready:break
                        await asyncio.sleep(.05)
                    assert co.control_runtime.ready
                    assert (await co.health())['control_leader'] is True
                    assert (await p['app'].fetchval('SELECT state FROM grid_runtime_state'))=='INFRA_ONLY'
                    assert await p['app'].fetchval("SELECT count(*) FROM service_leases WHERE service_key='control-plane-leader'")==1
                finally:await co.shutdown()
            async with p['owner'].acquire() as c:assert await catalog_digest(c)==before
    asyncio.run(run())


def test_two_runtime_candidates_and_fenced_takeover():
    async def run():
        from grid.control_runtime import ControlRuntime,FencedPool
        async with database() as (p,*_):
            starts=[]
            fenced=FencedPool(p['app'])
            async def start(epoch):
                await fenced.execute("INSERT INTO fleet_operations(id,action,status,requested_by) VALUES(gen_random_uuid(),'synthetic','test','ci')")
                starts.append(epoch)
            async def stop():pass
            a=ControlRuntime(p['app'],start,stop,node_id='synthetic-a')
            b=ControlRuntime(p['app'],start,stop,node_id='synthetic-b')
            a.start();b.start()
            try:
                for _ in range(100):
                    if a.ready or b.ready:break
                    await asyncio.sleep(.05)
                assert sum((a.ready,b.ready))==1 and len(starts)==1
                leader,follower=(a,b) if a.ready else (b,a)
                await leader.stop()
                assert await follower.election.campaign()
                await follower._gain(follower.election.epoch)
                assert follower.ready and len(starts)==2
                assert starts[1]>starts[0]
            finally:
                await a.stop();await b.stop()
    asyncio.run(run())


def test_app_connection_loss_can_reconnect_without_preparation():
    async def run():
        async with database() as (p,r,options,name,admin):
            c=await p['app'].acquire()
            pid=await c.fetchval('SELECT pg_backend_pid()')
            assert await admin.fetchval('SELECT pg_terminate_backend($1)',pid)
            await p['app'].release(c)
            await verify_runtime_schema(p['app'])
    asyncio.run(run())


def test_admin_owner_preparation_is_separate_from_runtime_authentication():
    async def run():
        async with database(False) as (p,r,options,name,admin):
            owner=await asyncpg.create_pool(**options,user='grid',database=name,min_size=1,max_size=1,
                                            server_settings={'role':r['owner']})
            try:assert await prepare_schema(owner)=='PREPARED'
            finally:await owner.close()
            await grant_runtime(p['owner'],r)
            substituted=await asyncpg.create_pool(**options,user='grid',database=name,min_size=1,max_size=1,
                                                  server_settings={'role':r['app']})
            try:
                with pytest.raises(SchemaBlocked,match='DDL_AUTHORITY'):
                    await verify_runtime_schema(substituted)
            finally:await substituted.close()
    asyncio.run(run())


def test_runtime_rejects_unprepared_database_without_creating_objects():
    async def run():
        async with database(False) as (p,*_):
            with pytest.raises(asyncpg.UndefinedTableError):
                await verify_runtime_schema(p['app'])
            assert await p['owner'].fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='public'")==0
    asyncio.run(run())


def test_missing_required_dml_privilege_blocks_startup():
    async def run():
        async with database() as (p,r,*_):
            await p['owner'].execute(f'REVOKE UPDATE ON public.fleet_operations FROM "{r["app"]}"')
            with pytest.raises(SchemaBlocked,match='DML_GRANTS_MISSING'):
                await verify_runtime_schema(p['app'])
    asyncio.run(run())
