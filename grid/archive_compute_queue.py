from __future__ import annotations
import json,uuid
from .strattester_bridge_protocol import digest


async def seed_archive_compute_jobs(pool,limit=500):
    created=0
    async with pool.acquire() as c:
        async with c.transaction():
            rows=await c.fetch("""SELECT b.symbol,b.archive_date,b.source_uri,b.sha256,b.bytes,i.tick_size
              FROM trade_archive_backfill b JOIN instruments i ON i.symbol=b.symbol
              WHERE b.status IN ('queued','retry') AND b.source_uri IS NOT NULL
              ORDER BY b.archive_date,b.symbol FOR UPDATE OF b SKIP LOCKED LIMIT $1""",int(limit))
            for row in rows:
                result=await c.execute("""INSERT INTO archive_compute_jobs
                  (id,symbol,archive_date,source_uri,expected_sha256,expected_bytes,tick_size)
                  VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(symbol,archive_date) DO NOTHING""",
                  uuid.uuid4(),row["symbol"],row["archive_date"],row["source_uri"],
                  row["sha256"],row["bytes"],float(row["tick_size"]))
                if result.endswith(" 1"):
                    await c.execute("""UPDATE trade_archive_backfill SET status='distributed',
                      updated_at=now(),last_error=NULL WHERE symbol=$1 AND archive_date=$2
                      AND status IN ('queued','retry')""",row["symbol"],row["archive_date"])
                    created+=1
    return created


async def claim_archive_compute_job(pool,node_id,lease_seconds=300):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM archive_compute_jobs
              WHERE status='queued' AND attempts<max_attempts
              ORDER BY archive_date,symbol FOR UPDATE SKIP LOCKED LIMIT 1""")
            if not row:return None
            job=await c.fetchrow("""UPDATE archive_compute_jobs SET status='running',
              lease_owner=$2,lease_until=now()+($3*interval '1 second'),
              lease_generation=lease_generation+1,attempts=attempts+1,updated_at=now()
              WHERE id=$1 RETURNING *""",row["id"],node_id,int(lease_seconds))
            return dict(job)


async def renew_archive_compute_job(pool,job_id,node_id,generation,lease_seconds=300):
    r=await pool.execute("""UPDATE archive_compute_jobs SET
      lease_until=now()+($4*interval '1 second'),updated_at=now()
      WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3
        AND status='running' AND lease_until>=now()""",
      job_id,node_id,int(generation),int(lease_seconds))
    return r.endswith(" 1")


async def archive_compute_lease_valid(pool,job_id,node_id,generation):
    return bool(await pool.fetchval("""SELECT EXISTS(
      SELECT 1 FROM archive_compute_jobs WHERE id=$1 AND lease_owner=$2
      AND lease_generation=$3 AND status='running' AND lease_until>=now())""",
      job_id,node_id,int(generation)))


async def attach_archive_compute_artifact(pool,job_id,node_id,generation,artifact_id):
    r=await pool.execute("""UPDATE archive_compute_jobs SET derived_artifact_id=$4,updated_at=now()
      WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3
        AND status='running' AND lease_until>=now()""",
      job_id,node_id,int(generation),artifact_id)
    return r.endswith(" 1")


async def fail_archive_compute_job(pool,job_id,node_id,generation,error):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""UPDATE archive_compute_jobs SET
              status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,
              lease_owner=NULL,lease_until=NULL,last_error=$4,updated_at=now()
              WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3 AND status='running'
              RETURNING symbol,archive_date,status""",
              job_id,node_id,int(generation),str(error)[:4000])
            if not row:return False
            if row["status"]=="failed":
                await c.execute("""UPDATE trade_archive_backfill SET status='failed',
                  last_error=$3,updated_at=now() WHERE symbol=$1 AND archive_date=$2""",
                  row["symbol"],row["archive_date"],str(error)[:4000])
            return True


async def accept_archive_compute_result(pool,job_id,node_id,generation,manifest):
    async with pool.acquire() as c:
        async with c.transaction():
            job=await c.fetchrow("""SELECT * FROM archive_compute_jobs WHERE id=$1
              AND lease_owner=$2 AND lease_generation=$3 AND status='running'
              AND lease_until>=now() FOR UPDATE""",job_id,node_id,int(generation))
            if not job:return False
            expected={"symbol":job["symbol"],"archive_date":str(job["archive_date"]),
                      "source_uri":job["source_uri"],"tick_size":float(job["tick_size"])}
            for key,value in expected.items():
                if manifest.get(key)!=value:raise ValueError(f"archive manifest {key} mismatch")
            if job["expected_sha256"] and manifest.get("source_sha256")!=job["expected_sha256"]:
                raise ValueError("archive source sha256 mismatch")
            if job["expected_bytes"] is not None and int(manifest.get("source_bytes",-1))!=int(job["expected_bytes"]):
                raise ValueError("archive source byte size mismatch")
            if int(manifest.get("source_rows",0))<0 or int(manifest.get("derived_candles",0))<0:
                raise ValueError("invalid archive result counts")
            artifact_id=manifest.get("derived_artifact_id")
            artifact_sha=str(manifest.get("derived_artifact_sha256") or "").lower()
            if not artifact_id or len(artifact_sha)!=64:
                raise ValueError("archive derived artifact is required")
            if not job["derived_artifact_id"] or str(job["derived_artifact_id"])!=str(artifact_id):
                raise ValueError("archive derived artifact id mismatch")
            artifact=await c.fetchrow("""SELECT storage_uri,status,bytes FROM ml_artifacts WHERE id=$1""",
                uuid.UUID(str(artifact_id)))
            if not artifact or artifact["status"]!="ACTIVE":
                raise ValueError("archive derived artifact is not active")
            if str(artifact["storage_uri"])!="content://sha256/"+artifact_sha:
                raise ValueError("archive derived artifact sha256 mismatch")
            if int(manifest.get("derived_artifact_bytes",-1))!=int(artifact["bytes"] or 0):
                raise ValueError("archive derived artifact byte size mismatch")
            result_hash=digest(manifest)
            await c.execute("""UPDATE archive_compute_jobs SET status='done',lease_until=NULL,
              result_manifest=$4::jsonb,result_hash=$5,last_error=NULL,updated_at=now()
              WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3""",
              job_id,node_id,int(generation),json.dumps(manifest),result_hash)
            return True


async def recover_archive_compute_jobs(pool):
    async with pool.acquire() as c:
        async with c.transaction():
            rows=await c.fetch("""UPDATE archive_compute_jobs SET
              status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,
              lease_owner=NULL,lease_until=NULL,last_error=COALESCE(last_error,'expired compute lease'),
              updated_at=now() WHERE status='running' AND lease_until<now()
              RETURNING symbol,archive_date,status,last_error""")
            for row in rows:
                if row["status"]=="failed":
                    await c.execute("""UPDATE trade_archive_backfill SET status='failed',
                      last_error=$3,updated_at=now() WHERE symbol=$1 AND archive_date=$2""",
                      row["symbol"],row["archive_date"],row["last_error"])
            return len(rows)

