"""PostgreSQL integration: transaction advisory locks serialize dispatchers."""
import asyncio
import os

import asyncpg
import pytest

from grid.ml_dispatcher import DISPATCH_LOCK_KEY


def test_dispatch_lock_serializes_and_releases_on_rollback():
    async def scenario():
        pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"], min_size=2, max_size=2)
        entered = asyncio.Event()
        release = asyncio.Event()
        acquired_second = asyncio.Event()

        async def first():
            async with pool.acquire() as conn:
                with pytest.raises(RuntimeError, match="forced rollback"):
                    async with conn.transaction():
                        await conn.execute("SELECT pg_advisory_xact_lock($1)", DISPATCH_LOCK_KEY)
                        entered.set()
                        await asyncio.wait_for(release.wait(), 5)
                        raise RuntimeError("forced rollback")

        async def second():
            await asyncio.wait_for(entered.wait(), 5)
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock($1)", DISPATCH_LOCK_KEY)
                    acquired_second.set()

        try:
            first_task = asyncio.create_task(first())
            await asyncio.wait_for(entered.wait(), 5)
            second_task = asyncio.create_task(second())
            await asyncio.sleep(0.15)
            assert not acquired_second.is_set(), "second dispatcher bypassed lock"
            release.set()
            await asyncio.wait_for(asyncio.gather(first_task, second_task), 5)
            assert acquired_second.is_set()
        finally:
            release.set()
            await pool.close()

    asyncio.run(scenario())


def test_two_dispatchers_respect_global_slots_and_node_capacity():
    import uuid
    from grid.ml_dispatcher import MLDispatcher

    async def scenario():
        schema="dispatch_test_"+uuid.uuid4().hex
        admin=await asyncpg.connect(os.environ["POSTGRES_DSN"])
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        async def setup(conn):
            await conn.execute(f'SET search_path TO "{schema}"')
        pool=None
        try:
            await admin.execute(f'''CREATE TABLE "{schema}".ml_jobs (
                id uuid PRIMARY KEY, status text NOT NULL, job_type text NOT NULL,
                payload jsonb, attempts int NOT NULL DEFAULT 0,
                max_attempts int NOT NULL DEFAULT 3,
                not_before timestamptz, priority int NOT NULL DEFAULT 1,
                created_at timestamptz NOT NULL DEFAULT now(),
                lease_owner text,lease_until timestamptz
            )''')
            await admin.execute(f'''CREATE TABLE "{schema}".ml_resource_reservations (
                job_id uuid PRIMARY KEY,node_id text NOT NULL,cpu double precision,
                ram_gb double precision,scratch_gb double precision,
                gpu boolean,expires_at timestamptz NOT NULL
            )''')
            for _ in range(4):
                await admin.execute(f'INSERT INTO "{schema}".ml_jobs(id,status,job_type,payload) VALUES($1,\'queued\',\'train\',$2::jsonb)',uuid.uuid4(),'{"cpu":4,"ram_gb":4,"scratch_gb":5}')
            pool=await asyncpg.create_pool(os.environ["POSTGRES_DSN"],min_size=2,max_size=4,init=setup)
            async def nodes():
                return {"pilot":{"cpu_pct":0,"cpu_count":8,
                                 "ram_available":12*1024**3,"disk_free":40*1024**3,
                                 "ml_runtime_ready":True}}
            first=MLDispatcher(pool,nodes)
            second=MLDispatcher(pool,nodes)
            a,b=await asyncio.wait_for(asyncio.gather(first(4),second(4)),10)
            assert len(a)+len(b)==2
            assert len({x["job_id"] for x in a+b})==2
            rows=await admin.fetch(f'SELECT status,count(*) AS n FROM "{schema}".ml_jobs GROUP BY status')
            counts={r["status"]:r["n"] for r in rows}
            assert counts=={"assigned":2,"queued":2}
            reservations=await admin.fetchrow(f"""SELECT count(*) AS jobs,sum(cpu) AS cpu,
                sum(ram_gb) AS ram_gb,sum(scratch_gb) AS scratch_gb
                FROM "{schema}".ml_resource_reservations""")
            assert reservations["jobs"]==2
            assert reservations["cpu"]==8
            assert reservations["ram_gb"]==8
            assert reservations["scratch_gb"]==10
        finally:
            if pool is not None:await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(scenario())
