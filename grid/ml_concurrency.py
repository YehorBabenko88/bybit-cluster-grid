from datetime import timedelta
import json,uuid

async def claim_ml_job(pool,owner,lease_seconds=120):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM ml_jobs
              WHERE (status='queued' OR (status='running' AND lease_until<now()))
              ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
            if not row: return None
            updated=await c.fetchrow("""UPDATE ml_jobs SET status='running',lease_owner=$2,
              lease_until=now()+($3*interval '1 second'),started_at=COALESCE(started_at,now()),
              attempts=attempts+1,error=NULL WHERE id=$1 RETURNING *""",
              row["id"],owner,int(lease_seconds))
            return dict(updated)

async def renew_ml_job(pool,job_id,owner,lease_seconds=120):
    r=await pool.execute("""UPDATE ml_jobs SET lease_until=now()+($3*interval '1 second')
      WHERE id=$1 AND status='running' AND lease_owner=$2 AND lease_until>=now()""",
      job_id,owner,int(lease_seconds))
    return r.endswith(" 1")

async def finish_ml_job(pool,job_id,owner,error=None):
    r=await pool.execute("""UPDATE ml_jobs SET status=$3,finished_at=now(),lease_until=NULL,error=$4
      WHERE id=$1 AND lease_owner=$2 AND status='running'""",
      job_id,owner,"failed" if error else "done",error)
    return r.endswith(" 1")

async def acquire_service_lease(pool,key,owner,lease_seconds=30,metadata=None):
    row=await pool.fetchrow("""INSERT INTO service_leases(service_key,owner,lease_until,metadata)
      VALUES($1,$2,now()+($3*interval '1 second'),$4::jsonb)
      ON CONFLICT(service_key) DO UPDATE SET owner=EXCLUDED.owner,
      lease_until=EXCLUDED.lease_until,heartbeat_at=now(),metadata=EXCLUDED.metadata
      WHERE service_leases.lease_until<now() OR service_leases.owner=EXCLUDED.owner
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
