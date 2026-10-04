from __future__ import annotations
import json,uuid
from .strattester_bridge_protocol import digest


async def seed_archive_compute_jobs(pool,limit=500):
    rows=await pool.fetch("""SELECT b.symbol,b.archive_date,b.source_uri,b.sha256,b.bytes,i.tick_size
      FROM trade_archive_backfill b JOIN instruments i ON i.symbol=b.symbol
      WHERE b.status IN ('queued','retry') AND b.source_uri IS NOT NULL
      ORDER BY b.archive_date,b.symbol LIMIT $1""",int(limit))
    created=0
    for row in rows:
        result=await pool.execute("""INSERT INTO archive_compute_jobs
          (id,symbol,archive_date,source_uri,expected_sha256,expected_bytes,tick_size)
          VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(symbol,archive_date) DO NOTHING""",
          uuid.uuid4(),row["symbol"],row["archive_date"],row["source_uri"],
          row["sha256"],row["bytes"],float(row["tick_size"]))
        if result.endswith(" 1"):created+=1
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


async def fail_archive_compute_job(pool,job_id,node_id,generation,error):
    r=await pool.execute("""UPDATE archive_compute_jobs SET
      status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,
      lease_owner=NULL,lease_until=NULL,last_error=$4,updated_at=now()
      WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3 AND status='running'""",
      job_id,node_id,int(generation),str(error)[:4000])
    return r.endswith(" 1")


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
            if int(manifest.get("source_rows",0))<0 or int(manifest.get("derived_candles",0))<0:
                raise ValueError("invalid archive result counts")
            result_hash=digest(manifest)
            await c.execute("""UPDATE archive_compute_jobs SET status='done',lease_until=NULL,
              result_manifest=$4::jsonb,result_hash=$5,last_error=NULL,updated_at=now()
              WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3""",
              job_id,node_id,int(generation),json.dumps(manifest),result_hash)
            return True


async def recover_archive_compute_jobs(pool):
    return await pool.execute("""UPDATE archive_compute_jobs SET
      status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,
      lease_owner=NULL,lease_until=NULL,last_error=COALESCE(last_error,'expired compute lease'),
      updated_at=now() WHERE status='running' AND lease_until<now()""")


async def cleanup_stale_archive_partials(root,ttl_seconds):
    import time
    from pathlib import Path
    root=Path(root)
    if not root.exists():return 0
    cutoff=time.time()-float(ttl_seconds);deleted=0
    for p in root.rglob("*.part"):
        try:
            if p.stat().st_mtime<cutoff:
                p.unlink();deleted+=1
        except FileNotFoundError:
            pass
    return deleted
