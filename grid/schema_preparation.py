"""Explicit trusted-owner schema preparation; never imported by startup.

Default CLI is plan-only. Connection configuration is inherited from a protected
environment/passfile, never accepted as a command-line credential.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager

from .db import Database
from .migrations import apply_migrations
from .schema_contract import CONTRACT_VERSION, SchemaBlocked, source_digest, catalog_digest, verify_schema


class ConnectionPool:
    """Reuse the single serialized transaction in existing preparation helpers."""
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    def __getattr__(self, name):
        return getattr(self.connection, name)


async def prepare_schema(pool):
    from .instrument_lifecycle import ensure_instrument_schema
    from .strategy_jobs import ensure_strategy_schema
    from .strategy_plugins import ensure_plugin_schema
    from .control_plane import ensure_control_schema
    from .update_protocol import ensure_update_schema
    from .enrollment import ensure_enrollment_schema
    from .runtime_gate import ensure_runtime_gate
    from .retention import ensure_retention_schema
    from .fleet_control import ensure_fleet_schema
    async with pool.acquire() as c:
        # Same lock as migrations, held across baseline, supplemental and seal.
        await c.execute('SELECT pg_advisory_lock($1)', 0x42594347)
        try:
            async with c.transaction():
                await c.execute('SET LOCAL search_path=public,pg_catalog')
                if not await c.fetchval("""SELECT datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)
                      FROM pg_database WHERE datname=current_database()"""):
                    raise SchemaBlocked('PREPARATION_REQUIRES_DATABASE_OWNER')
                if await c.fetchval("SELECT to_regclass('public.grid_schema_contract') IS NOT NULL"):
                    await verify_schema(c)
                    return 'ALREADY_PREPARED'
                if await c.fetchval("""SELECT EXISTS(SELECT 1 FROM pg_depend
                     WHERE refclassid='pg_namespace'::regclass AND refobjid='public'::regnamespace
                       AND deptype='n')
                     OR EXISTS(SELECT 1 FROM pg_namespace WHERE substr(nspname,1,3)<>'pg_'
                               AND nspname NOT IN ('public','information_schema'))"""):
                    raise SchemaBlocked('UNSEALED_EXISTING_SCHEMA_REQUIRES_REVIEW')
                adapter = ConnectionPool(c)
                db = Database()
                db.pool = adapter
                await db.ensure_schema()
                await apply_migrations(adapter)
                for ensure in (ensure_instrument_schema, ensure_strategy_schema, ensure_plugin_schema,
                               ensure_control_schema, ensure_update_schema, ensure_enrollment_schema,
                               ensure_runtime_gate, ensure_retention_schema, ensure_fleet_schema):
                    await ensure(adapter)
                await c.execute("""CREATE TABLE public.grid_schema_contract(
                    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
                    version integer NOT NULL,source_sha256 text NOT NULL,catalog_sha256 text NOT NULL)
                """)
                await c.execute('REVOKE ALL ON public.grid_schema_contract FROM PUBLIC')
                await c.execute('INSERT INTO public.grid_schema_contract VALUES(true,$1,$2,$3)',
                                CONTRACT_VERSION, source_digest(), await catalog_digest(c))
                await verify_schema(c)
            return 'PREPARED'
        finally:
            await c.execute('SELECT pg_advisory_unlock($1)', 0x42594347)


async def _execute(expected_database):
    db = Database()
    try:
        await db.connect()
        if await db.pool.fetchval('SELECT current_database()') != expected_database:
            raise SchemaBlocked('PREPARATION_DATABASE_NAME_MISMATCH')
        print(await prepare_schema(db.pool))
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='explicit owner-authorized schema preparation')
    parser.add_argument('--database', help='required exact target database name; never a DSN')
    args = parser.parse_args()
    if not args.execute:
        print('PLAN_ONLY: baseline + migrations 1-48 + supplemental schema + contract; no connection')
        return
    try:
        if not args.database:
            parser.error('--database is required with --execute')
        asyncio.run(_execute(args.database))
    except Exception:
        # asyncpg exceptions can contain credentials, SQL or local paths.
        parser.exit(1, 'SCHEMA_PREPARATION_FAILED: preserve evidence; no automatic repair or downgrade\n')


if __name__ == '__main__':
    main()
