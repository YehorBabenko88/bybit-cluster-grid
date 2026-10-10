from datetime import timedelta

PERMANENT_CODES={"DATASET_HASH_MISMATCH","INVALID_DATASET","SCHEMA_ERROR","UNSUPPORTED_JOB"}
def retry_delay_seconds(attempt,base=30,cap=1800):
    return min(int(cap),int(base)*(2**max(0,int(attempt)-1)))

def classify_failure(exc):
    code=getattr(exc,"code",None)
    if code in PERMANENT_CODES:return "permanent",str(code)
    if isinstance(exc,(ValueError,KeyError,TypeError)):return "permanent",code or exc.__class__.__name__
    return "retryable",code or exc.__class__.__name__

async def fail_or_retry(pool,job_id,owner,generation,error,kind="retryable"):
    # Fence the owner and generation while transitioning state and releasing
    # capacity. A concurrent takeover cannot be undone by an old worker.
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT attempts,max_attempts FROM ml_jobs
              WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3
                AND status='running' AND lease_until>=clock_timestamp()
              FOR UPDATE""",job_id,owner,int(generation))
            if not row:
                return "stale"
            terminal=kind=="permanent" or row["attempts"]>=row["max_attempts"]
            if terminal:
                result=await c.execute("""UPDATE ml_jobs SET status='failed',
                  finished_at=clock_timestamp(),lease_until=NULL,error=$4
                  WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3
                    AND status='running'""",
                  job_id,owner,int(generation),str(error)[:4000])
                state="failed"
            else:
                delay=retry_delay_seconds(row["attempts"])
                result=await c.execute("""UPDATE ml_jobs SET status='queued',
                  lease_owner=NULL,lease_until=NULL,
                  not_before=clock_timestamp()+($4*interval '1 second'),error=$5
                  WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3
                    AND status='running'""",
                  job_id,owner,int(generation),delay,str(error)[:4000])
                state="retry"
            if not result.endswith(" 1"):
                return "stale"
            await c.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",job_id)
            return state
