"""Integration uses ONLY an explicitly supplied disposable DSN and private schema."""
import asyncio
import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('HISTORY_DISPOSABLE_DSN'),
                                reason='explicit disposable PostgreSQL not configured')


def _disposable_dsn(environ):
    fixed = 'postgresql://grid:grid@127.0.0.1:5432/grid'
    expected = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                'GITHUB_REPOSITORY': 'YehorBabenko88/bybit-cluster-grid',
                'GITHUB_JOB': 'linux-postgres18', 'HISTORY_DISPOSABLE_DSN': fixed,
                'MISSION3_TEST_DATABASE_URL': fixed}
    if any(environ.get(key) != value for key, value in expected.items()):
        raise ValueError('DISPOSABLE_PG_JOB_REQUIRED')
    return fixed


def test_durable_callback_replay_rate_limit_and_closed_audit():
    async def scenario():
        import asyncpg
        from grid.telegram_ingress_migration import MIGRATION49SQL
        from grid.telegram_idempotency import admit_update, finish_update
        schema = 'telegram_disposable_' + uuid.uuid4().hex
        dsn = _disposable_dsn(os.environ)
        admin = await asyncpg.connect(dsn, server_settings={'search_path': 'pg_catalog'})
        pool = None
        created = False
        public_before = await admin.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            created = True
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3,
                                            server_settings={'search_path': schema})
            # Startup server_settings survive pool RESET ALL, unlike init-only SET.
            for _ in range(4):
                async with pool.acquire() as checkout:
                    assert await checkout.fetchval('SELECT current_schema()') == schema
                    assert await checkout.fetchval('SELECT current_schemas(false)') == [schema]
            await pool.execute('''CREATE TABLE telegram_updates(update_id bigint PRIMARY KEY,
                chat_id text,command text,claimed_by text,status text DEFAULT 'CLAIMED',
                completed_at timestamptz,error text)''')
            for sql in MIGRATION49SQL:
                await pool.execute(sql)
            accepted = await admit_update(pool, 1, -100, 42, '/status', 'test',
                                          callback_id='private-callback-token', authorized=True)
            assert accepted.decision == 'ACCEPTED'
            assert (await admit_update(pool,1,-100,42,'/status','replacement',
                callback_id='private-callback-token',authorized=False)).decision == 'STUCK'
            assert (await admit_update(pool,1,-100,43,'/status','replacement',
                callback_id='changed',authorized=True)).decision == 'STUCK'
            assert (await admit_update(pool,2,-100,43,'/status','replacement',
                callback_id='private-callback-token',authorized=True)).decision == 'STUCK'
            assert not await finish_update(pool, 1, 'x'*64)
            assert await finish_update(pool, 1, accepted.receipt)
            # Same durable state is observed through a fresh connection/leader.
            assert (await admit_update(pool, 1, -100, 42, '/status', 'replacement',
                                      callback_id='private-callback-token', authorized=True)).decision == 'DUPLICATE'
            assert (await admit_update(pool, 2, -100, 43, '/status', 'replacement',
                                      callback_id='private-callback-token', authorized=True)).decision == 'REPLAY'
            assert await pool.fetchval('SELECT count(*) FROM telegram_updates') == 1
            # Parallel leaders must share the same durable actor budget.
            decisions = await asyncio.gather(*(admit_update(pool, 100+i, -100, 99, '/status', 'test',
                                                           authorized=True) for i in range(35)))
            assert sum(result.decision=='ACCEPTED' for result in decisions) == 30
            assert sum(result.decision=='RATE_LIMITED' for result in decisions) == 5
            await pool.execute("UPDATE telegram_actor_limits SET window_start=clock_timestamp()-interval '61 seconds' WHERE user_id=99")
            later = await admit_update(pool, 200, -100, 99, '/status', 'replacement', authorized=True)
            assert later.decision == 'ACCEPTED'
            assert (await admit_update(pool, 201, -100, 42, '/stop private-token', 'test', authorized=False)).decision == 'DENIED'
            await finish_update(pool, 200, later.receipt, failed=True)
            rows = await pool.fetch('SELECT operation,decision FROM telegram_ingress_audit')
            assert all(row['decision'] in {'ACCEPTED','DONE','FAILED','DUPLICATE','REPLAY','DENIED','RATE_LIMITED','STUCK','CAPACITY'} for row in rows)
            assert all('private' not in row['operation'] for row in rows)
            assert await pool.fetchval('SELECT error FROM telegram_updates WHERE update_id=200') == 'FAILED'
            for _ in range(4):
                async with pool.acquire() as checkout:
                    assert await checkout.fetchval('SELECT current_schema()') == schema
            public_after = await admin.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            assert public_after == public_before
        finally:
            if pool: await pool.close()
            # schema is generated here, never accepted from user/environment data.
            if created:
                await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(scenario())
