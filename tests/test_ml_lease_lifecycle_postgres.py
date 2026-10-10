"""Real PostgreSQL integration coverage for ML reservation lease lifecycle."""
import asyncio
import os
import uuid

import asyncpg

from grid.ml_concurrency import renew_ml_job, finish_ml_job
from grid.ml_retry import fail_or_retry
from grid.ml_worker_protocol import accept_assigned_job
from grid.ml_orchestrator_service import MLOrchestratorService


def test_ml_reservations_renew_finish_and_recovery_postgres():
    async def scenario():
        schema="ml_lease_test_"+uuid.uuid4().hex
        admin=await asyncpg.connect(os.environ["POSTGRES_DSN"])
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool=None
        async def init(conn):
            await conn.execute(f'SET search_path TO "{schema}"')
        async def add_job(status, owner, generation, lease_offset, reservation_offset,
                          attempts=1, max_attempts=3):
            job_id=uuid.uuid4()
            await admin.execute(f"""INSERT INTO "{schema}".ml_jobs
              (id,status,lease_owner,lease_generation,lease_until,attempts,max_attempts)
              VALUES($1,$2,$3,$4,clock_timestamp()+($5*interval '1 second'),$6,$7)""",
              job_id,status,owner,generation,lease_offset,attempts,max_attempts)
            await admin.execute(f"""INSERT INTO "{schema}".ml_resource_reservations
              (job_id,node_id,cpu,ram_gb,scratch_gb,gpu,expires_at)
              VALUES($1,'pilot',1,2,3,false,clock_timestamp()+($2*interval '1 second'))""",
              job_id,reservation_offset)
            return job_id
        async def reservation(job_id):
            return await admin.fetchval(
              f'SELECT expires_at FROM "{schema}".ml_resource_reservations WHERE job_id=$1',job_id)
        try:
            await admin.execute(f"""CREATE TABLE "{schema}".ml_jobs (
              id uuid PRIMARY KEY,status text NOT NULL,lease_owner text,
              lease_generation integer NOT NULL DEFAULT 1,lease_until timestamptz,
              attempts integer NOT NULL DEFAULT 1,max_attempts integer NOT NULL DEFAULT 3,
              not_before timestamptz,finished_at timestamptz,error text,
              started_at timestamptz,priority integer NOT NULL DEFAULT 1,
              created_at timestamptz NOT NULL DEFAULT clock_timestamp())""")
            await admin.execute(f"""CREATE TABLE "{schema}".ml_resource_reservations (
              job_id uuid PRIMARY KEY,node_id text,cpu double precision,ram_gb double precision,
              scratch_gb double precision,gpu boolean,expires_at timestamptz)""")
            await admin.execute(f"""CREATE TABLE "{schema}".service_leases (
              service_key text PRIMARY KEY,owner text NOT NULL,
              lease_until timestamptz NOT NULL,heartbeat_at timestamptz,
              metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb)""")
            pool=await asyncpg.create_pool(os.environ["POSTGRES_DSN"],min_size=1,max_size=3,setup=init)
            live=await add_job("running","worker-a",3,60,15)
            old_expiry=await reservation(live)
            assert not await renew_ml_job(pool,live,"stale-worker",2,120)
            assert await reservation(live)==old_expiry
            assert await renew_ml_job(pool,live,"worker-a",3,180)
            new_expiry=await reservation(live)
            assert new_expiry>old_expiry
            assert not await finish_ml_job(pool,live,"stale-worker",2)
            assert await reservation(live)==new_expiry
            assert await finish_ml_job(pool,live,"worker-a",3)
            assert await reservation(live) is None
            assert await admin.fetchval(f'SELECT status FROM "{schema}".ml_jobs WHERE id=$1',live)=="done"

            assigned=await add_job("assigned","pilot",0,60,20)
            accepted=await accept_assigned_job(pool,"pilot",lease_seconds=180)
            assert accepted is not None
            assert accepted["id"]==assigned
            assert accepted["status"]=="running"
            assert accepted["lease_generation"]==1
            assert await reservation(assigned)==accepted["lease_until"]
            assert await accept_assigned_job(pool,"pilot") is None
            assert await finish_ml_job(pool,assigned,"pilot",1)
            assert await reservation(assigned) is None

            competing=await add_job("assigned","pilot",7,60,30)
            winner,loser=await asyncio.gather(
                accept_assigned_job(pool,"pilot",lease_seconds=120),
                accept_assigned_job(pool,"pilot",lease_seconds=120),
            )
            accepted_jobs=[job for job in (winner,loser) if job is not None]
            assert len(accepted_jobs)==1
            assert accepted_jobs[0]["id"]==competing
            assert accepted_jobs[0]["lease_generation"]==8
            assert await reservation(competing)==accepted_jobs[0]["lease_until"]
            assert await finish_ml_job(pool,competing,"pilot",8)
            assert await reservation(competing) is None

            retry_job=await add_job("running","retry-owner",4,60,60)
            assert await fail_or_retry(pool,retry_job,"old-owner",3,"stale")=="stale"
            assert await reservation(retry_job) is not None
            assert await fail_or_retry(pool,retry_job,"retry-owner",4,"transient")=="retry"
            assert await reservation(retry_job) is None
            assert await admin.fetchval(
                f'SELECT status FROM "{schema}".ml_jobs WHERE id=$1',retry_job)=="queued"
            permanent_job=await add_job("running","permanent-owner",5,60,60)
            assert await fail_or_retry(pool,permanent_job,"permanent-owner",5,"bad data","permanent")=="failed"
            assert await reservation(permanent_job) is None

            expired=await add_job("running","worker-old",1,-30,600)
            exhausted=await add_job("assigned","pilot",1,-30,600,3,3)
            healthy=await add_job("running","worker-live",2,600,600)
            orphan=await add_job("done","worker-old",1,-30,600)
            async def dispatcher(*args): return []
            async def health(): return {}
            service=MLOrchestratorService(pool,dispatcher,health)
            assert await __import__('grid.ml_concurrency',fromlist=['acquire_service_lease']).acquire_service_lease(pool,'ml-orchestrator-leader',service.owner)
            await service.recover()
            # A new orchestrator must preserve a live worker's lease.
            restarted=MLOrchestratorService(pool,dispatcher,health)
            await admin.execute(f"""UPDATE "{schema}".service_leases SET lease_until=clock_timestamp()-interval '1 second' WHERE service_key='ml-orchestrator-leader'""")
            assert await __import__('grid.ml_concurrency',fromlist=['acquire_service_lease']).acquire_service_lease(pool,'ml-orchestrator-leader',restarted.owner)
            await restarted.recover()
            assert await admin.fetchval(f'SELECT status FROM "{schema}".ml_jobs WHERE id=$1',healthy)=="running"
            assert await reservation(healthy) is not None
            # A crashed worker stops renewing; a later pass requeues it.
            crashed=await add_job("running","crashed-node",6,60,600)
            await admin.execute(f'UPDATE "{schema}".ml_jobs SET lease_until=clock_timestamp()-make_interval(secs=>1) WHERE id=$1',crashed)
            await restarted.recover()
            assert await admin.fetchval(f'SELECT status FROM "{schema}".ml_jobs WHERE id=$1',crashed)=="queued"
            assert await reservation(crashed) is None
            assert not await renew_ml_job(pool,crashed,"crashed-node",6)
            assert not await finish_ml_job(pool,crashed,"crashed-node",6)
            rows=await admin.fetch(f'SELECT id,status,lease_owner,lease_until,not_before FROM "{schema}".ml_jobs')
            jobs={row["id"]:row for row in rows}
            assert jobs[expired]["status"]=="queued"
            assert jobs[expired]["lease_owner"] is None
            assert jobs[expired]["not_before"] is not None
            assert jobs[exhausted]["status"]=="failed"
            assert jobs[healthy]["status"]=="running"
            assert await reservation(expired) is None
            assert await reservation(exhausted) is None
            assert await reservation(orphan) is None
            assert await reservation(healthy) is not None
        finally:
            if pool is not None: await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(scenario())
