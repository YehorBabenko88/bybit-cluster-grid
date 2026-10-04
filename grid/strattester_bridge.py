from __future__ import annotations
import json,uuid
from .strattester_bridge_protocol import digest,validate_manifest


async def create_research_run(pool,*,kind,dataset_id,dataset_hash,config,strattester_version,shards):
    run_id=uuid.uuid4(); config_hash=digest(config or {})
    async with pool.acquire() as c:
        async with c.transaction():
            if dataset_id is not None:
                ds=await c.fetchrow("SELECT status,dataset_hash FROM dataset_snapshots WHERE id=$1",dataset_id)
                if not ds or ds["status"]!="READY": raise ValueError("research requires READY dataset")
                if str(ds["dataset_hash"])!=str(dataset_hash): raise ValueError("research dataset hash mismatch")
            await c.execute("""INSERT INTO research_runs
              (id,kind,dataset_id,dataset_hash,config,config_hash,strattester_version,status)
              VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,'BUILDING')""",
              run_id,kind,dataset_id,dataset_hash,json.dumps(config or {}),config_hash,strattester_version)
            seen=set()
            for shard in shards:
                key=str(shard["shard_key"])
                if key in seen: raise ValueError("duplicate research shard key")
                seen.add(key); sid=uuid.uuid4(); spec=dict(shard.get("input_spec") or {})
                await c.execute("""INSERT INTO research_shards
                  (id,run_id,job_type,shard_key,input_spec,input_hash)
                  VALUES($1,$2,$3,$4,$5::jsonb,$6)""",
                  sid,run_id,shard["job_type"],key,json.dumps(spec),digest(spec))
            await c.execute("UPDATE research_runs SET status='QUEUED' WHERE id=$1",run_id)
    return str(run_id)


async def enqueue_research_shards(pool,run_id):
    run=await pool.fetchrow("SELECT * FROM research_runs WHERE id=$1",run_id)
    if not run or run["status"] not in ("QUEUED","RUNNING"): return 0
    rows=await pool.fetch("""SELECT * FROM research_shards
      WHERE run_id=$1 AND status='queued' ORDER BY job_type,shard_key""",run_id)
    created=0
    for row in rows:
        payload={"research_run_id":str(run_id),"research_shard_id":str(row["id"]),
                 "job_type":row["job_type"],"shard_key":row["shard_key"],
                 "dataset_hash":run["dataset_hash"],"config_hash":run["config_hash"],
                 "input_hash":row["input_hash"],"input_spec":dict(row["input_spec"] or {}),
                 "strattester_version":run["strattester_version"]}
        result=await pool.execute("""INSERT INTO ml_jobs(id,job_type,payload,status,dedupe_key)
          VALUES($1,'strattester',$2::jsonb,'queued',$3) ON CONFLICT DO NOTHING""",
          uuid.uuid4(),json.dumps(payload),f"strattester:{row['id']}")
        if result.endswith(" 1"): created+=1
    if created:
        await pool.execute("""UPDATE research_runs SET status='RUNNING',
          started_at=COALESCE(started_at,now()) WHERE id=$1 AND status='QUEUED'""",run_id)
    return created


async def accept_research_result(pool,shard_id,manifest):
    async with pool.acquire() as c:
        async with c.transaction():
            shard=await c.fetchrow("""SELECT s.*,r.dataset_hash,r.config_hash,r.strattester_version
              FROM research_shards s JOIN research_runs r ON r.id=s.run_id
              WHERE s.id=$1 FOR UPDATE""",shard_id)
            if not shard: raise ValueError("unknown research shard")
            expected={"run_id":str(shard["run_id"]),"job_id":str(shard["id"]),
                      "job_type":shard["job_type"],"dataset_hash":shard["dataset_hash"],
                      "code_version":shard["strattester_version"],
                      "config_hash":shard["config_hash"],"input_hash":shard["input_hash"]}
            validate_manifest(manifest,expected)
            if shard["status"]=="done":
                if shard["result_hash"]!=manifest["result_hash"]:
                    raise ValueError("completed shard result hash conflict")
                return False
            await c.execute("""UPDATE research_shards SET status='done',result_manifest=$2::jsonb,
              result_hash=$3,finished_at=now() WHERE id=$1""",
              shard_id,json.dumps(manifest),manifest["result_hash"])
            counts=await c.fetchrow("""SELECT count(*) FILTER(WHERE status='done') done,
              count(*) FILTER(WHERE status='failed') failed,
              count(*) FILTER(WHERE status NOT IN ('done','failed')) pending
              FROM research_shards WHERE run_id=$1""",shard["run_id"])
            if counts["pending"]==0:
                state="COMPLETE" if counts["failed"]==0 else "FAILED"
                await c.execute("""UPDATE research_runs SET status=$2,finished_at=now()
                  WHERE id=$1""",shard["run_id"],state)
            return True


async def claim_assigned_strattester_job(pool,node_id,lease_seconds=120):
    async with pool.acquire() as conn:
        async with conn.transaction():
            row=await conn.fetchrow("""SELECT * FROM ml_jobs
              WHERE job_type='strattester' AND status='assigned'
                AND lease_owner=$1 AND lease_until>=now()
              ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1""",node_id)
            if not row:return None
            job=await conn.fetchrow("""UPDATE ml_jobs SET status='running',
              started_at=COALESCE(started_at,now()),lease_until=now()+($3*interval '1 second'),
              attempts=attempts+1,lease_generation=lease_generation+1
              WHERE id=$1 AND lease_owner=$2 RETURNING *""",
              row["id"],node_id,int(lease_seconds))
            await conn.execute("""UPDATE ml_resource_reservations SET lease_generation=$2,
              expires_at=now()+($3*interval '1 second') WHERE job_id=$1""",
              row["id"],job["lease_generation"],int(lease_seconds))
            return dict(job)


async def renew_strattester_job(pool,job_id,node_id,lease_generation,lease_seconds=120):
    changed=await pool.execute("""UPDATE ml_jobs SET lease_until=now()+($3*interval '1 second')
      WHERE id=$1 AND lease_owner=$2 AND lease_generation=$4 AND job_type='strattester'
        AND status='running' AND lease_until>=now()""",
      job_id,node_id,int(lease_seconds),int(lease_generation))
    ok=changed.endswith(" 1")
    if ok:
        await pool.execute("""UPDATE ml_resource_reservations
          SET expires_at=now()+($2*interval '1 second'),lease_generation=$3 WHERE job_id=$1""",
          job_id,int(lease_seconds),int(lease_generation))
    return ok


async def complete_strattester_job(pool,job_id,node_id,lease_generation,manifest):
    async with pool.acquire() as conn:
        async with conn.transaction():
            job=await conn.fetchrow("""SELECT * FROM ml_jobs WHERE id=$1 AND job_type='strattester'
              AND lease_owner=$2 AND lease_generation=$3 AND status='running'
              AND lease_until>=now() FOR UPDATE""",
              job_id,node_id,int(lease_generation))
            if not job:return False
            payload=dict(job["payload"] or {})
            shard_id=payload.get("research_shard_id")
            if not shard_id:raise ValueError("strattester job missing research_shard_id")
            shard=await conn.fetchrow("""SELECT s.*,r.dataset_hash,r.config_hash,r.strattester_version
              FROM research_shards s JOIN research_runs r ON r.id=s.run_id
              WHERE s.id=$1 FOR UPDATE""",uuid.UUID(str(shard_id)))
            if not shard:raise ValueError("unknown research shard")
            expected={"run_id":str(shard["run_id"]),"job_id":str(shard["id"]),
                      "job_type":shard["job_type"],"dataset_hash":shard["dataset_hash"],
                      "code_version":shard["strattester_version"],
                      "config_hash":shard["config_hash"],"input_hash":shard["input_hash"]}
            validate_manifest(manifest,expected)
            if shard["status"]=="done":
                if shard["result_hash"]!=manifest["result_hash"]:
                    raise ValueError("completed shard result hash conflict")
            else:
                await conn.execute("""UPDATE research_shards SET status='done',
                  result_manifest=$2::jsonb,result_hash=$3,finished_at=now() WHERE id=$1""",
                  shard["id"],json.dumps(manifest),manifest["result_hash"])
            await conn.execute("""UPDATE ml_jobs SET status='done',finished_at=now(),
              lease_until=NULL,error=NULL WHERE id=$1""",job_id)
            await conn.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",job_id)
            counts=await conn.fetchrow("""SELECT count(*) FILTER(WHERE status='done') done,
              count(*) FILTER(WHERE status='failed') failed,
              count(*) FILTER(WHERE status NOT IN ('done','failed')) pending
              FROM research_shards WHERE run_id=$1""",shard["run_id"])
            if counts["pending"]==0:
                state="COMPLETE" if counts["failed"]==0 else "FAILED"
                await conn.execute("""UPDATE research_runs SET status=$2,finished_at=now()
                  WHERE id=$1""",shard["run_id"],state)
            return True
