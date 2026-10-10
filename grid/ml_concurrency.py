import json,uuid

async def claim_ml_job(pool,owner,lease_seconds=120):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM ml_jobs
              WHERE (status='queued' OR (status='running' AND lease_until<clock_timestamp()))
                AND attempts<max_attempts AND (not_before IS NULL OR not_before<=clock_timestamp())
              ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
            if not row: return None
            # Legacy direct claims may take over an expired running job.
            # Its previous node's reservation must not survive that takeover.
            if row.get("status")=="running":
                await c.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",row["id"])
            updated=await c.fetchrow("""UPDATE ml_jobs SET status='running',lease_owner=$2,
              lease_until=clock_timestamp()+($3*interval '1 second'),started_at=COALESCE(started_at,clock_timestamp()),
              attempts=attempts+1,lease_generation=lease_generation+1,error=NULL WHERE id=$1 RETURNING *""",
              row["id"],owner,int(lease_seconds))
            return dict(updated)

async def renew_ml_job(pool,job_id,owner,lease_generation,lease_seconds=120):
    # Keep the reservation alive for the same period as the running lease.
    # Both writes commit or roll back together; stale owners cannot extend it.
    async with pool.acquire() as c:
        async with c.transaction():
            r=await c.execute("""UPDATE ml_jobs SET lease_until=clock_timestamp()+($3*interval '1 second')
              WHERE id=$1 AND status='running' AND lease_owner=$2 AND lease_generation=$4
                AND lease_until>=clock_timestamp()""",
              job_id,owner,int(lease_seconds),int(lease_generation))
            if not r.endswith(" 1"):
                return False
            await c.execute("""UPDATE ml_resource_reservations SET
              expires_at=(SELECT lease_until FROM ml_jobs WHERE id=$1)
              WHERE job_id=$1""",job_id)
            return True

async def finish_ml_job(pool,job_id,owner,lease_generation,error=None):
    # Only the current generation may finish and release its reservation.
    async with pool.acquire() as c:
        async with c.transaction():
            r=await c.execute("""UPDATE ml_jobs SET status=$3,finished_at=clock_timestamp(),
              lease_until=NULL,error=$4
              WHERE id=$1 AND lease_owner=$2 AND lease_generation=$5
                AND status='running' AND lease_until>=clock_timestamp()""",
              job_id,owner,"failed" if error else "done",error,int(lease_generation))
            if not r.endswith(" 1"):
                return False
            await c.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",job_id)
            return True

async def acquire_service_lease(pool,key,owner,lease_seconds=30,metadata=None):
    row=await pool.fetchrow("""INSERT INTO service_leases(service_key,owner,lease_until,metadata)
      VALUES($1,$2,clock_timestamp()+($3*interval '1 second'),$4::jsonb)
      ON CONFLICT(service_key) DO UPDATE SET owner=EXCLUDED.owner,
      lease_until=EXCLUDED.lease_until,heartbeat_at=clock_timestamp(),metadata=EXCLUDED.metadata
      WHERE service_leases.lease_until<clock_timestamp() OR service_leases.owner=EXCLUDED.owner
      RETURNING owner,lease_until""",key,owner,int(lease_seconds),json.dumps(metadata or {}))
    return bool(row and row["owner"]==owner)

async def make_dataset_snapshot(pool,purpose,owner,criteria=None,safety_lag_seconds=120):
    # Freeze a wall-clock cutoff behind ingestion. Writers continue beyond it; readers use <= cutoff.
    row=await pool.fetchrow("""SELECT LEAST(
      COALESCE((SELECT max(ts) FROM candles_1m),now()),
      COALESCE((SELECT max(ts) FROM market_features_1m),now()),
      now()-($1*interval '1 second')) AS cutoff""",int(safety_lag_seconds))
    cutoff=row["cutoff"]; sid=uuid.uuid4()
    await pool.execute("""INSERT INTO dataset_snapshots(id,purpose,cutoff_ts,created_by,criteria)
      VALUES($1,$2,$3,$4,$5::jsonb)""",sid,purpose,cutoff,owner,json.dumps(criteria or {}))
    return {"id":str(sid),"cutoff_ts":cutoff}
