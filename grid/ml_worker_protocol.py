import asyncio
from .ml_retry import fail_or_retry,classify_failure
from .ml_concurrency import renew_ml_job,finish_ml_job

async def accept_assigned_job(pool,node_id,lease_seconds=120):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM ml_jobs
              WHERE status='assigned' AND lease_owner=$1 AND lease_until>=clock_timestamp()
              ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1""",node_id)
            if not row:return None
            job=dict(await c.fetchrow("""UPDATE ml_jobs SET status='running',
              started_at=COALESCE(started_at,now()),lease_until=clock_timestamp()+($3*interval '1 second'),
              attempts=attempts+1,lease_generation=lease_generation+1 WHERE id=$1 AND lease_owner=$2 RETURNING *""",
              row["id"],node_id,int(lease_seconds)))
            await c.execute("""UPDATE ml_resource_reservations SET lease_generation=$2,
              expires_at=clock_timestamp()+($3*interval '1 second') WHERE job_id=$1""",
              row["id"],job["lease_generation"],int(lease_seconds))
            return job

async def renew_running_job(pool,job_id,node_id,lease_generation,lease_seconds=120):
    return await renew_ml_job(pool,job_id,node_id,lease_generation,lease_seconds)


async def complete_running_job(pool,job_id,node_id,lease_generation,error=None):
    return await finish_ml_job(pool,job_id,node_id,lease_generation,error)


async def fail_running_job(pool,job_id,node_id,lease_generation,exc):
    kind,code=classify_failure(exc)
    state=await fail_or_retry(pool,job_id,node_id,lease_generation,f"{code}: {exc}",kind)
    if state in ("failed","retry"):
        await pool.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",job_id)
    return state


async def run_with_lease(pool,job,node_id,work,lease_seconds=120,renew_every=None):
    # Run an async ML workload while continuously fencing it with its DB lease.
    # Any loss of lease supervision, including a database exception, must cancel
    # the workload so a stale process cannot keep consuming resources.
    generation=int(job["lease_generation"])
    interval=float(renew_every or max(5,lease_seconds/3))
    task=asyncio.create_task(work())
    try:
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task),timeout=interval)
            except asyncio.TimeoutError:
                if not await renew_running_job(
                    pool,job["id"],node_id,generation,lease_seconds=lease_seconds
                ):
                    raise RuntimeError("ML job lease lost during execution")
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task,return_exceptions=True)
