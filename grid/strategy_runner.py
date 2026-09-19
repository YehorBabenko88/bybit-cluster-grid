import asyncio, logging
from .resources import NODE_ID
from .strategy_jobs import claim_job, finish_job, requeue_job, recover_stale_jobs
from .strategy_executor import execute_job_subprocess
from .strategy_resources import strategy_allowed, database_pressure
from .config import settings
from .background_guard import background_work_allowed

log=logging.getLogger("strategy_runner")

async def strategy_worker(db,poll_seconds=None):
    poll_seconds=poll_seconds or settings.strategy_poll_seconds
    await recover_stale_jobs(db.pool,settings.strategy_job_timeout_seconds)
    last_recovery=asyncio.get_running_loop().time()
    while True:
        now=asyncio.get_running_loop().time()
        if now-last_recovery>=60:
            await recover_stale_jobs(db.pool,settings.strategy_job_timeout_seconds)
            last_recovery=now
        job=None
        try:
            bg_ok,bg_reasons=await background_work_allowed(db.pool)
            if not bg_ok:
                log.info("strategy paused by shared workload guard",extra={
                    "event":"strategy_shared_pause","component":",".join(bg_reasons)
                })
                await asyncio.sleep(max(3,poll_seconds)); continue
            ok,snap,reasons=strategy_allowed(settings)
            if not ok:
                log.info("strategy paused by resource guard",extra={
                    "event":"strategy_resource_pause","component":",".join(reasons)
                })
                await asyncio.sleep(max(3,poll_seconds)); continue

            dbp=await database_pressure(db.pool,settings)
            if not dbp["ok"]:
                log.info("strategy paused by db pressure",extra={
                    "event":"strategy_db_pause","component":str(dbp)
                })
                await asyncio.sleep(max(3,poll_seconds)); continue

            job=await claim_job(db.pool,NODE_ID)
            if not job:
                await asyncio.sleep(poll_seconds); continue

            # Re-check immediately before expensive work.
            ok,_,reasons=strategy_allowed(settings)
            if not ok:
                await requeue_job(db.pool,job["id"],"resource pressure: "+",".join(reasons))
                job=None
                await asyncio.sleep(max(3,poll_seconds)); continue

            await execute_job_subprocess(db,job)
            await finish_job(db.pool,job["id"])
            log.info("strategy job completed",extra={"event":"strategy_job_done","component":str(job["id"])})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("strategy job failed",extra={"event":"strategy_job_failed"})
            if job:
                await finish_job(db.pool,job["id"],str(e))
            await asyncio.sleep(1)
