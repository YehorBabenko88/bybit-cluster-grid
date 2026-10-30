"""Real adversarial SQL, only in the independently attested disposable CI DB.

Baseline mode deliberately proves vulnerabilities; its PASS is NOT acceptance.
The identical probes in candidate mode must fail closed.
"""
import asyncio
import os

import asyncpg
import pytest
from _pg18_database import database
from grid.schema_contract import SchemaBlocked, catalog_digest, verify_runtime_schema
from grid.schema_preparation import prepare_schema

pytestmark = pytest.mark.skipif(os.environ.get('GRID_PG18_TESTS') != '1',
                               reason='attested disposable PG18 CI only')
BASELINE = os.environ.get('PR227_BASELINE_REPRO') == '1'


async def rejected(pool):
    if BASELINE:
        await verify_runtime_schema(pool)
    else:
        with pytest.raises(SchemaBlocked):
            await verify_runtime_schema(pool)


@pytest.mark.parametrize('privilege', ['TRIGGER', 'TRUNCATE', 'REFERENCES', 'MAINTAIN'])
def test_extra_table_authority(privilege):
    async def run():
        async with database() as (p, roles, *_):
            await p['owner'].execute(f'GRANT {privilege} ON public.market_events TO "{roles["app"]}"')
            await rejected(p['app'])
            if BASELINE and privilege == 'TRIGGER':
                # Actual non-owner DDL, not merely a privilege-query assertion.
                await p['app'].execute('''CREATE TRIGGER adversarial BEFORE UPDATE ON public.market_events
                    FOR EACH ROW EXECUTE FUNCTION pg_catalog.suppress_redundant_updates_trigger()''')
    asyncio.run(run())


def test_rewrite_rule_drift():
    async def run():
        async with database() as (p, *_):
            before = await catalog_digest(p['owner'])
            await p['owner'].execute('''CREATE RULE ignore_deletes AS ON DELETE TO public.market_events
                                       DO INSTEAD NOTHING''')
            assert (await catalog_digest(p['owner']) == before) is BASELINE
            await rejected(p['app'])
            if BASELINE:
                assert await prepare_schema(p['owner']) == 'ALREADY_PREPARED'
            else:
                with pytest.raises(SchemaBlocked):
                    await prepare_schema(p['owner'])
    asyncio.run(run())


def test_foreign_metadata_column_writer():
    async def run():
        async with database() as (p, roles, *_):
            await p['owner'].execute(f'GRANT UPDATE(catalog_sha256) ON public.grid_schema_contract TO "{roles["ro"]}"')
            await rejected(p['app'])
    asyncio.run(run())


def test_foreign_metadata_owner_reseal():
    async def run():
        async with database() as (p, roles, options, name, _):
            # Owner transfer is a trusted-admin drift, not ordinary app authority.
            admin = await asyncpg.connect(**options, user='grid', database=name)
            try:
                await admin.execute(f'ALTER TABLE public.grid_schema_contract OWNER TO "{roles["ro"]}"')
            finally:
                await admin.close()
            digest = await catalog_digest(p['ro'])
            await p['ro'].execute('UPDATE public.grid_schema_contract SET catalog_sha256=$1', digest)
            await rejected(p['app'])
    asyncio.run(run())


def test_sequence_update_authority():
    async def run():
        async with database() as (p, roles, *_):
            await p['owner'].execute(f'GRANT UPDATE ON ALL SEQUENCES IN SCHEMA public TO "{roles["app"]}"')
            await rejected(p['app'])
    asyncio.run(run())


@pytest.mark.parametrize('privilege', ['SET', 'ALTER SYSTEM'])
def test_parameter_authority(privilege):
    async def run():
        async with database() as (p, roles, _, __, admin):
            role = roles['app']
            try:
                await admin.execute(f'GRANT {privilege} ON PARAMETER session_replication_role TO "{role}"')
                await rejected(p['app'])
                if BASELINE and privilege == 'SET':
                    async with p['app'].acquire() as c:
                        async with c.transaction():
                            await c.execute('SET LOCAL session_replication_role=replica')
                            assert await c.fetchval('SHOW session_replication_role') == 'replica'
            finally:
                # Global parameter ACL must be removed before disposable role cleanup.
                await admin.execute(f'REVOKE {privilege} ON PARAMETER session_replication_role FROM "{role}"')
    asyncio.run(run())


def test_default_privileges_do_not_create_foreign_seal_writer():
    async def run():
        async with database(False) as (p, roles, *_):
            await p['owner'].execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT UPDATE ON TABLES TO "{roles["ro"]}"')
            if BASELINE:
                assert await prepare_schema(p['owner']) == 'PREPARED'
                assert await p['ro'].fetchval("SELECT has_column_privilege(current_user,'public.grid_schema_contract','catalog_sha256','UPDATE')")
            else:
                with pytest.raises(SchemaBlocked, match='ISSUER_UNTRUSTED'):
                    await prepare_schema(p['owner'])
                assert await p['owner'].fetchval("SELECT to_regclass('public.schema_migrations')") is None
    asyncio.run(run())


def test_callable_foreign_security_definer():
    async def run():
        async with database() as (p, roles, *_):
            await p['owner'].execute('CREATE SCHEMA adversarial')
            await p['owner'].execute(f'GRANT USAGE ON SCHEMA adversarial TO "{roles["app"]}"')
            await p['owner'].execute('''CREATE FUNCTION adversarial.escalate() RETURNS void
                LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog
                AS 'CREATE TABLE public.unexpected_ddl(id int)' ''')
            await rejected(p['app'])
            if BASELINE:
                await p['app'].execute('SELECT adversarial.escalate()')
                assert await p['app'].fetchval("SELECT to_regclass('public.unexpected_ddl') IS NOT NULL")
    asyncio.run(run())
