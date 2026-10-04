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
    if kind=="permanent":
        r=await pool.execute("""UPDATE ml_jobs SET status='failed',finished_at=now(),lease_until=NULL,
          error=$5 WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3 AND status='running'
          AND lease_until>=now()""",job_id,owner,int(generation),0,str(error)[:4000])
        return "failed" if r.endswith(" 1") else "stale"
    row=await pool.fetchrow("""SELECT attempts,max_attempts FROM ml_jobs WHERE id=$1 AND lease_owner=$2
      AND lease_generation=$3 AND status='running' AND lease_until>=now()""",job_id,owner,int(generation))
    if not row:return "stale"
    if row["attempts"]>=row["max_attempts"]:
        await pool.execute("""UPDATE ml_jobs SET status='failed',finished_at=now(),lease_until=NULL,error=$2
          WHERE id=$1 AND lease_generation=$3""",job_id,str(error)[:4000],int(generation))
        return "failed"
    delay=retry_delay_seconds(row["attempts"])
    await pool.execute("""UPDATE ml_jobs SET status='queued',lease_owner=NULL,lease_until=NULL,
      not_before=now()+($2*interval '1 second'),error=$3 WHERE id=$1 AND lease_generation=$4""",
      job_id,delay,str(error)[:4000],int(generation))
    return "retry"


async def recover_expired_ml_jobs(pool):
    # One atomic SQL statement claims expired rows with SKIP LOCKED and performs
    # their state transition.  It works both with asyncpg Pool and Connection,
    # and competing CONTROL instances cannot recover the same lease twice.
    rows=await pool.fetch("""WITH expired AS (
        SELECT id,attempts,max_attempts FROM ml_jobs
        WHERE status IN ('assigned','running') AND lease_until<now()
        ORDER BY lease_until,id FOR UPDATE SKIP LOCKED
      ), changed AS (
        UPDATE ml_jobs j SET
          status=CASE WHEN e.attempts>=e.max_attempts THEN 'failed' ELSE 'queued' END,
          finished_at=CASE WHEN e.attempts>=e.max_attempts THEN now() ELSE NULL END,
          lease_owner=NULL,lease_until=NULL,
          not_before=CASE WHEN e.attempts>=e.max_attempts THEN j.not_before ELSE now() END,
          error=COALESCE(j.error,'expired compute lease')
        FROM expired e WHERE j.id=e.id
        RETURNING j.id,j.status
      )
      SELECT id,status FROM changed""")
    recovered=failed=0
    for row in rows:
        if str(row["status"])=="failed":failed+=1
        else:recovered+=1
        await pool.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",row["id"])
    return {"recovered":recovered,"failed":failed}
