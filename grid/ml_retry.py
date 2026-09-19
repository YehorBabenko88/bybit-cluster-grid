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
