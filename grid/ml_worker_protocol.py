async def accept_assigned_job(pool,node_id,lease_seconds=120):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM ml_jobs
              WHERE status='assigned' AND lease_owner=$1 AND lease_until>=now()
              ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1""",node_id)
            if not row:return None
            return dict(await c.fetchrow("""UPDATE ml_jobs SET status='running',
              started_at=COALESCE(started_at,now()),lease_until=now()+($3*interval '1 second'),
              attempts=attempts+1,lease_generation=lease_generation+1 WHERE id=$1 AND lease_owner=$2 RETURNING *""",
              row["id"],node_id,int(lease_seconds)))

async def renew_running_job(pool,job_id,node_id,lease_generation,lease_seconds=120):
    r=await pool.execute("""UPDATE ml_jobs SET lease_until=now()+($3*interval '1 second')
      WHERE id=$1 AND lease_owner=$2 AND lease_generation=$4 AND status='running' AND lease_until>=now()""",
      job_id,node_id,int(lease_seconds),int(lease_generation))
    return r.endswith(" 1")

async def complete_running_job(pool,job_id,node_id,lease_generation,error=None):
    r=await pool.execute("""UPDATE ml_jobs SET status=$3,finished_at=now(),lease_until=NULL,error=$4
      WHERE id=$1 AND lease_owner=$2 AND lease_generation=$5 AND status='running' AND lease_until>=now()""",
      job_id,node_id,"failed" if error else "done",error,int(lease_generation))
    return r.endswith(" 1")
