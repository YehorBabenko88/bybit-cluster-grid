import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest

from grid.ml_training_worker import TrainingWorker,StaleTrainingLease
from grid.strategy_runtime import StrategyContext
from grid.strategy_jobs import ensure_strategy_schema,claim_job,finish_job,requeue_job
from test_collection_ownership_postgres import database

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='disposable CI database only')


async def model_schema(pool):
    await pool.execute("""CREATE TABLE ml_jobs(id uuid PRIMARY KEY,status text,lease_owner text,
      lease_generation bigint,lease_until timestamptz)""")
    await pool.execute("""CREATE TABLE model_registry(id uuid PRIMARY KEY,model_family text,dataset_id uuid,
      status text,artifact_id uuid,code_version text,feature_version text,hyperparameters jsonb)""")


def test_raw_training_cannot_publish_after_waiting_past_lease():
    async def run():
        async with database() as pool:
            await model_schema(pool);jid=uuid.uuid4()
            await pool.execute("INSERT INTO ml_jobs VALUES($1,'running','node',1,clock_timestamp()+interval '150 milliseconds')",jid)
            async with pool.acquire() as blocker:
                tx=blocker.transaction();await tx.start()
                await blocker.fetchrow('SELECT id FROM ml_jobs WHERE id=$1 FOR UPDATE',jid)
                worker=TrainingWorker(pool,None,'test')
                task=asyncio.create_task(worker._publish_candidate(uuid.uuid4(),'global',uuid.uuid4(),uuid.uuid4(),'v1',{},
                                                                 job_id=jid,lease_owner='node',lease_generation=1))
                await asyncio.sleep(.25);await tx.rollback()
                with pytest.raises(StaleTrainingLease):await task
            assert await pool.fetchval('SELECT count(*) FROM model_registry')==0
    asyncio.run(run())


def test_strategy_attempt_returned_by_claim_and_stale_completion_is_fenced():
    async def run():
        async with database() as pool:
            await ensure_strategy_schema(pool)
            jid=uuid.uuid4()
            await pool.execute("INSERT INTO strategy_jobs(id,strategy_name,attempts) VALUES($1,'test',1)",jid)
            job=await claim_job(pool,'node')
            assert job['attempts']==2 and job['status']=='running'
            await StrategyContext(pool,job).emit('BTCUSDT',datetime.now(timezone.utc),'test',{'ok':True})
            assert await pool.fetchval('SELECT count(*) FROM strategy_results')==1
            await finish_job(pool,jid,assigned_node='node',attempts=1)
            await requeue_job(pool,jid,'stale',assigned_node='node',attempts=1)
            assert await pool.fetchval('SELECT status FROM strategy_jobs WHERE id=$1',jid)=='running'
            await finish_job(pool,jid,assigned_node='node',attempts=2)
            assert await pool.fetchval('SELECT status FROM strategy_jobs WHERE id=$1',jid)=='done'
    asyncio.run(run())


def test_strategy_deferred_commit_exceeding_attempt_deadline_is_rolled_back(monkeypatch):
    from grid.strategy_runtime import settings
    monkeypatch.setattr(settings,'strategy_job_timeout_seconds',1)
    async def run():
        async with database() as pool:
            await ensure_strategy_schema(pool);jid=uuid.uuid4()
            await pool.execute("""INSERT INTO strategy_jobs(id,strategy_name,status,assigned_node,attempts,started_at)
              VALUES($1,'test','running','node',1,clock_timestamp()-interval '850 milliseconds')""",jid)
            await pool.execute("""CREATE FUNCTION slow_commit() RETURNS trigger LANGUAGE plpgsql AS $$
              BEGIN PERFORM pg_sleep(.5);RETURN NEW;END $$""")
            await pool.execute("""CREATE CONSTRAINT TRIGGER slow_strategy_commit AFTER INSERT ON strategy_results
              DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION slow_commit()""")
            with pytest.raises(RuntimeError):
                await StrategyContext(pool,{'id':jid,'assigned_node':'node','attempts':1}).emit(
                    'BTCUSDT',datetime.now(timezone.utc),'test',{})
            assert await pool.fetchval('SELECT count(*) FROM strategy_results')==0
    asyncio.run(run())


def test_strategy_expired_attempt_cannot_report_done():
    async def run():
        async with database() as pool:
            await ensure_strategy_schema(pool);jid=uuid.uuid4()
            await pool.execute("""INSERT INTO strategy_jobs(id,strategy_name,status,assigned_node,attempts,started_at)
              VALUES($1,'test','running','node',1,clock_timestamp()-interval '1 day')""",jid)
            await finish_job(pool,jid,assigned_node='node',attempts=1)
            assert await pool.fetchval('SELECT status FROM strategy_jobs WHERE id=$1',jid)=='running'
    asyncio.run(run())


def test_raw_training_deadline_covers_deferred_commit():
    async def run():
        async with database() as pool:
            await model_schema(pool);jid=uuid.uuid4()
            await pool.execute("""CREATE FUNCTION slow_commit() RETURNS trigger LANGUAGE plpgsql AS $$
              BEGIN PERFORM pg_sleep(.5);RETURN NEW;END $$""")
            await pool.execute("""CREATE CONSTRAINT TRIGGER slow_model_commit AFTER INSERT ON model_registry
              DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION slow_commit()""")
            await pool.execute("INSERT INTO ml_jobs VALUES($1,'running','node',1,clock_timestamp()+interval '150 milliseconds')",jid)
            worker=TrainingWorker(pool,None,'test')
            with pytest.raises(StaleTrainingLease):
                await worker._publish_candidate(uuid.uuid4(),'global',uuid.uuid4(),uuid.uuid4(),'v1',{},
                                                job_id=jid,lease_owner='node',lease_generation=1)
            assert await pool.fetchval('SELECT count(*) FROM model_registry')==0
    asyncio.run(run())


def test_strategy_fetch_is_readonly_and_stale_emit_is_rejected():
    async def run():
        async with database() as pool:
            await pool.execute("""CREATE TABLE strategy_jobs(id uuid PRIMARY KEY,status text,
              assigned_node text,attempts integer,started_at timestamptz)""")
            await pool.execute("""CREATE TABLE strategy_results(job_id uuid,symbol text,ts timestamptz,
              result_type text,payload jsonb,PRIMARY KEY(job_id,symbol,ts,result_type))""")
            jid=uuid.uuid4()
            await pool.execute("INSERT INTO strategy_jobs VALUES($1,'running','new-node',2,clock_timestamp())",jid)
            context=StrategyContext(pool,{'id':jid,'assigned_node':'old-node','attempts':1})
            with pytest.raises(Exception):await context.fetch("INSERT INTO canonical_writes VALUES('bad',1) RETURNING *")
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
            with pytest.raises(RuntimeError):
                await context.emit('BTCUSDT',None,'test',{})
            assert await pool.fetchval('SELECT count(*) FROM strategy_results')==0
    asyncio.run(run())
