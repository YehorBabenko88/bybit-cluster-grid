import asyncio, importlib.util, json, os, sys
import asyncpg
from .job_write_fence import job_write
from .config import settings
from .db import configure_connection
from .schema_contract import verify_runtime_schema

class StrategyContext:
    def __init__(self,pool,job):
        self.pool=pool
        self.job=job

    async def fetch(self,sql,*args):
        # Production should use a PostgreSQL read-only role for market-data access.
        async with self.pool.acquire() as c:
            async with c.transaction(readonly=True):
                return await c.fetch(sql,*args)

    async def emit(self,symbol,ts,result_type,payload):
        async with job_write(self.pool,'strategy',self.job['id'],self.job.get('assigned_node'),
                             self.job.get('attempts'),settings.strategy_job_timeout_seconds) as c:
            await c.execute("""INSERT INTO strategy_results(job_id,symbol,ts,result_type,payload)
              VALUES($1,$2,$3,$4,$5::jsonb)
              ON CONFLICT(job_id,symbol,ts,result_type)
              DO UPDATE SET payload=EXCLUDED.payload""",
              self.job["id"],symbol,ts,result_type,json.dumps(payload))

async def main():
    plugin_path=os.environ["GRID_STRATEGY_PLUGIN"]
    job_id=os.environ["GRID_STRATEGY_JOB_ID"]
    dsn=os.environ["POSTGRES_DSN"]
    attempt=int(os.environ['GRID_STRATEGY_ATTEMPT'])
    node=os.environ['GRID_STRATEGY_NODE']

    pool=await asyncpg.create_pool(dsn,min_size=1,max_size=3,command_timeout=60,
                                   setup=configure_connection)
    try:
        await verify_runtime_schema(pool)
        async with pool.acquire() as c:
            row=await c.fetchrow("SELECT * FROM strategy_jobs WHERE id=$1::uuid",job_id)
            if not row: raise RuntimeError("job not found")
            job=dict(row)
            if job['status']!='running' or job['assigned_node']!=node or job['attempts']!=attempt:
                raise RuntimeError('strategy attempt is no longer current')
        spec=importlib.util.spec_from_file_location("grid_hot_strategy",plugin_path)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        run=getattr(mod,"run",None)
        if run is None:
            raise RuntimeError("strategy plugin must define async def run(ctx)")
        ctx=StrategyContext(pool,job)
        result=run(ctx)
        if asyncio.iscoroutine(result):
            await result
        else:
            raise RuntimeError("strategy run(ctx) must be async")
    finally:
        await pool.close()

if __name__=="__main__":
    asyncio.run(main())
