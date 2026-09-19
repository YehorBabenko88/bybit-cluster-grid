import asyncio, json, logging
from .resources import NODE_ID
from .strategy_jobs import claim_job, finish_job

log=logging.getLogger("strategy_runner")

class StrategyRegistry:
    def __init__(self):
        self._strategies={}
    def register(self,name,fn):
        self._strategies[name]=fn
    def get(self,name):
        return self._strategies.get(name)

registry=StrategyRegistry()

async def run_job(db,job):
    fn=registry.get(job["strategy_name"])
    if fn is None:
        raise ValueError(f"unknown strategy: {job['strategy_name']}")
    params=job["params"] if isinstance(job["params"],dict) else json.loads(job["params"])
    symbols=job["symbols"] if isinstance(job["symbols"],list) else json.loads(job["symbols"])
    await fn(db,job["id"],symbols,job["start_ts"],job["end_ts"],params)

async def strategy_worker(db,poll_seconds=3):
    while True:
        job=None
        try:
            job=await claim_job(db.pool,NODE_ID)
            if not job:
                await asyncio.sleep(poll_seconds); continue
            await run_job(db,job)
            await finish_job(db.pool,job["id"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("strategy job failed",extra={"event":"strategy_job_failed"})
            if job:
                await finish_job(db.pool,job["id"],str(e))
            await asyncio.sleep(1)
