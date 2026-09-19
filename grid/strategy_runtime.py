import asyncio, importlib.util, json, os, sys
import asyncpg

class StrategyContext:
    def __init__(self,pool,job):
        self.pool=pool
        self.job=job

    async def fetch(self,sql,*args):
        # Production should use a PostgreSQL read-only role for market-data access.
        async with self.pool.acquire() as c:
            return await c.fetch(sql,*args)

    async def emit(self,symbol,ts,result_type,payload):
        async with self.pool.acquire() as c:
            await c.execute("""INSERT INTO strategy_results(job_id,symbol,ts,result_type,payload)
              VALUES($1,$2,$3,$4,$5::jsonb)
              ON CONFLICT(job_id,symbol,ts,result_type)
              DO UPDATE SET payload=EXCLUDED.payload""",
              self.job["id"],symbol,ts,result_type,json.dumps(payload))

async def main():
    plugin_path=os.environ["GRID_STRATEGY_PLUGIN"]
    job_id=os.environ["GRID_STRATEGY_JOB_ID"]
    dsn=os.environ["POSTGRES_DSN"]

    spec=importlib.util.spec_from_file_location("grid_hot_strategy",plugin_path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run=getattr(mod,"run",None)
    if run is None:
        raise RuntimeError("strategy plugin must define async def run(ctx)")

    pool=await asyncpg.create_pool(dsn,min_size=1,max_size=3,command_timeout=60)
    try:
        async with pool.acquire() as c:
            row=await c.fetchrow("SELECT * FROM strategy_jobs WHERE id=$1::uuid",job_id)
            if not row: raise RuntimeError("job not found")
            job=dict(row)
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
