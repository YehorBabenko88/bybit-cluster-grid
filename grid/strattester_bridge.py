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
