"""Real SQL fixtures: attestation MUST precede connection and CREATE DATABASE."""
from contextlib import asynccontextmanager
import os
import uuid
import asyncpg
from tools.ci_pg18 import attest
from grid.db import configure_connection


@asynccontextmanager
async def database(prepared=True):
    identity = attest()  # no connection on failed/missing proof
    options = dict(host='127.0.0.1', port=int(os.environ['GRID_PG18_PORT']),
                   password=os.environ['GRID_PG18_PASSWORD'], command_timeout=15)
    admin = await asyncpg.connect(**options,user='grid',database='grid',
                                 server_settings={'default_transaction_read_only':'on'})
    name='ddl18_'+uuid.uuid4().hex
    roles={k:name+'_'+k for k in ('owner','app','ro')}
    pools={}
    created_roles=[]
    created_database=False
    try:
        if await admin.fetchval('SELECT system_identifier::text FROM pg_catalog.pg_control_system()') != identity:
            raise RuntimeError('PG18_HOST_CLUSTER_IDENTITY_MISMATCH_NO_MUTATIONS')
        if await admin.fetchval('SHOW server_version_num') != '180004':
            raise RuntimeError('PG18_VERSION_MISMATCH_NO_MUTATIONS')
        await admin.execute('SET default_transaction_read_only=off')
        for role in roles.values():
            # Synthetic per-run random credential, masked by provider. No DSN/argv/artifact secret.
            secret=os.environ['GRID_PG18_PASSWORD']
            assert len(secret)==64 and all(ch in '0123456789abcdef' for ch in secret)
            await admin.execute(f'CREATE ROLE "{role}" LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD \'{secret}\'')
            created_roles.append(role)
        await admin.execute(f'CREATE DATABASE "{name}" OWNER "{roles["owner"]}" TEMPLATE template0')
        created_database=True
        await admin.execute(f'REVOKE ALL ON DATABASE "{name}" FROM PUBLIC')
        for role in roles.values():
            await admin.execute(f'GRANT CONNECT ON DATABASE "{name}" TO "{role}"')
        for kind,role in roles.items():
            pools[kind]=await asyncpg.create_pool(**options,user=role,database=name,
                                                 min_size=1,max_size=4,setup=configure_connection)
        owner=pools['owner']
        await owner.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
        await owner.execute(f'GRANT USAGE ON SCHEMA public TO "{roles["app"]}","{roles["ro"]}"')
        if prepared:
            from grid.schema_preparation import prepare_schema
            await prepare_schema(owner)
            await grant_runtime(owner,roles)
        yield pools,roles,options,name,admin
    finally:
        for p in pools.values():
            await p.close()
        # Cleanup is limited to this context's generated names in attested CI.
        if created_database:
            await admin.execute(f'DROP DATABASE "{name}"')
        for role in created_roles:
            await admin.execute(f'DROP ROLE "{role}"')
        await admin.close()


async def grant_runtime(owner, roles):
    app,ro=roles['app'],roles['ro']
    await owner.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO "{app}"')
    await owner.execute(f'REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.grid_schema_contract,public.schema_migrations FROM "{app}"')
    await owner.execute(f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO "{app}"')
    await owner.execute(f'GRANT SELECT ON public.candles_1m,public.footprint_1m,public.derivatives_metrics TO "{ro}"')
