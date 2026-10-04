from __future__ import annotations
import json,uuid
from .strattester_bridge_protocol import canonical_json,digest,input_digest,validate_manifest,aggregate_fingerprint
from .compute_artifacts import publish_compute_bytes


def validate_distributed_input(job_type,spec):
    spec=dict(spec or {})
    if str(job_type)=="strategy_backtest":
        if spec.get("local_market_db") or spec.get("local_results_db"):
            raise ValueError("distributed strategy_backtest cannot contain worker-local database paths")
        sha=str(spec.get("dataset_sha256") or "").lower()
        if len(sha)!=64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise ValueError("distributed strategy_backtest requires dataset_sha256")
    return spec


def validate_shard_dag(shards):
    if not shards: raise ValueError("research run requires at least one shard")
    by_key={}
    for shard in shards:
        key=str(shard["shard_key"])
        if key in by_key: raise ValueError("duplicate research shard key")
        by_key[key]=shard
    for key,shard in by_key.items():
        for dep in shard.get("depends_on") or []:
            dep=str(dep)
            if dep not in by_key: raise ValueError(f"unknown dependency {dep} for {key}")
            if dep==key: raise ValueError("research shard cannot depend on itself")
    visiting=set();done=set()
    def visit(key):
        if key in done:return
        if key in visiting:raise ValueError("research shard dependency cycle")
        visiting.add(key)
        for dep in by_key[key].get("depends_on") or []:visit(str(dep))
        visiting.remove(key);done.add(key)
    for key in by_key:visit(key)
    return by_key


async def create_research_run(pool,*,kind,dataset_id,dataset_hash,config,strattester_version,shards,dataset_artifact_id=None):
    run_id=uuid.uuid4(); config_hash=digest(config or {})
    async with pool.acquire() as c:
        async with c.transaction():
            if dataset_id is None:
                raise ValueError("distributed research requires an immutable dataset_id")
            ds=await c.fetchrow("SELECT status,dataset_hash,artifact_id FROM dataset_snapshots WHERE id=$1",dataset_id)
            if not ds or ds["status"]!="READY": raise ValueError("research requires READY dataset")
            if str(ds["dataset_hash"])!=str(dataset_hash): raise ValueError("research dataset hash mismatch")
            dataset_artifact_sha=None
            dataset_artifact_uuid=None
            if dataset_artifact_id is None and ds["artifact_id"] is not None:
                dataset_artifact_id=ds["artifact_id"]
            if dataset_artifact_id is not None:
                dataset_artifact_uuid=uuid.UUID(str(dataset_artifact_id))
                art=await c.fetchrow("""SELECT storage_uri,status FROM ml_artifacts WHERE id=$1""",
                    dataset_artifact_uuid)
                if not art or art["status"]!="ACTIVE":
                    raise ValueError("distributed dataset artifact is not active")
                uri=str(art["storage_uri"] or "")
                prefix="content://sha256/"
                if not uri.startswith(prefix):
                    raise ValueError("distributed dataset artifact is not content-addressed")
                dataset_artifact_sha=uri[len(prefix):]
            await c.execute("""INSERT INTO research_runs
              (id,kind,dataset_id,dataset_hash,config,config_hash,strattester_version,status,dataset_artifact_id)
              VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,'BUILDING',$8)""",
              run_id,kind,dataset_id,dataset_hash,json.dumps(config or {}),config_hash,strattester_version,dataset_artifact_uuid)
            by_key=validate_shard_dag(shards)
            shard_ids={key:uuid.uuid4() for key in by_key}
            for key,shard in by_key.items():
                spec=dict(shard.get("input_spec") or {})
                if str(shard["job_type"])=="strategy_backtest" and dataset_artifact_sha:
                    if spec.get("dataset_sha256") and str(spec["dataset_sha256"]).lower()!=dataset_artifact_sha.lower():
                        raise ValueError("shard dataset_sha256 conflicts with research dataset artifact")
                    spec["dataset_artifact_id"]=str(dataset_artifact_uuid)
                    spec["dataset_sha256"]=dataset_artifact_sha
                elif str(shard["job_type"])=="strategy_backtest" and spec.get("dataset_artifact_id") and not spec.get("dataset_sha256"):
                    art=await c.fetchrow("""SELECT storage_uri,status FROM ml_artifacts WHERE id=$1""",
                        uuid.UUID(str(spec["dataset_artifact_id"])))
                    if not art or art["status"]!="ACTIVE":
                        raise ValueError("distributed dataset artifact is not active")
                    uri=str(art["storage_uri"] or "")
                    prefix="content://sha256/"
                    if not uri.startswith(prefix):
                        raise ValueError("distributed dataset artifact is not content-addressed")
                    spec["dataset_sha256"]=uri[len(prefix):]
                spec=validate_distributed_input(shard["job_type"],spec)
                await c.execute("""INSERT INTO research_shards
                  (id,run_id,job_type,shard_key,input_spec,input_hash)
                  VALUES($1,$2,$3,$4,$5::jsonb,$6)""",
                  shard_ids[key],run_id,shard["job_type"],key,json.dumps(spec),input_digest(spec))
            for key,shard in by_key.items():
                for dep in shard.get("depends_on") or []:
                    await c.execute("""INSERT INTO research_shard_dependencies
                      (run_id,shard_id,depends_on_id) VALUES($1,$2,$3)""",
                      run_id,shard_ids[key],shard_ids[str(dep)])
            await c.execute("UPDATE research_runs SET status='QUEUED' WHERE id=$1",run_id)
    return str(run_id)


def strategy_backtest_shards(*,symbols,strategies,start_ms,end_ms):
    symbols=tuple(sorted({str(x).strip().upper() for x in symbols if str(x).strip()}))
    strategies=tuple(sorted({str(x).strip() for x in strategies if str(x).strip()}))
    if not symbols:raise ValueError("backtest research requires symbols")
    if not strategies:raise ValueError("backtest research requires strategies")
    start_ms=int(start_ms);end_ms=int(end_ms)
    if end_ms<start_ms:raise ValueError("backtest end precedes start")
    return [{
        "shard_key":f"strategy:{strategy}:symbol:{symbol}",
        "job_type":"strategy_backtest",
        "input_spec":{"symbol":symbol,"strategy":strategy,"start_ms":start_ms,"end_ms":end_ms},
    } for strategy in strategies for symbol in symbols]


async def create_strategy_backtest_research(pool,*,dataset_id,strategies,strattester_version,
    symbols=None,config=None):
    ds=await pool.fetchrow("""SELECT id,status,dataset_hash,artifact_id,criteria
      FROM dataset_snapshots WHERE id=$1""",dataset_id)
    if not ds or ds["status"]!="READY":raise ValueError("backtest requires READY dataset snapshot")
    if ds["artifact_id"] is None:raise ValueError("backtest dataset snapshot has no artifact")
    criteria=dict(ds["criteria"] or {})
    available=tuple(criteria.get("symbols") or ())
    selected=tuple(symbols or available)
    if not selected:raise ValueError("backtest dataset has no symbols")
    missing=sorted(set(str(x).upper() for x in selected)-set(str(x).upper() for x in available))
    if missing:raise ValueError("backtest symbols outside dataset: "+",".join(missing))
    start=str(criteria.get("start_ts") or "");end=str(criteria.get("end_ts") or "")
    if not start or not end:raise ValueError("backtest dataset is missing frozen time bounds")
    from datetime import datetime
    def to_ms(value):
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        return int(round(dt.timestamp()*1000))
    shards=strategy_backtest_shards(symbols=selected,strategies=strategies,
        start_ms=to_ms(start),end_ms=to_ms(end))
    return await create_research_run(pool,kind="strategy_backtest",dataset_id=ds["id"],
        dataset_hash=ds["dataset_hash"],config=config or {},
        strattester_version=strattester_version,shards=shards,
        dataset_artifact_id=ds["artifact_id"])


async def enqueue_research_shards(pool,run_id):
    run=await pool.fetchrow("SELECT * FROM research_runs WHERE id=$1",run_id)
    if not run or run["status"] not in ("QUEUED","RUNNING"): return 0
    rows=await pool.fetch("""SELECT s.* FROM research_shards s
      WHERE s.run_id=$1 AND s.status='queued'
        AND NOT EXISTS(
          SELECT 1 FROM research_shard_dependencies d
          JOIN research_shards parent ON parent.id=d.depends_on_id
          WHERE d.shard_id=s.id AND parent.status<>'done')
      ORDER BY s.job_type,s.shard_key""",run_id)
    created=0
    for row in rows:
        payload={"research_run_id":str(run_id),"research_shard_id":str(row["id"]),
                 "job_type":row["job_type"],"shard_key":row["shard_key"],
                 "dataset_hash":run["dataset_hash"],"config":dict(run["config"] or {}),"config_hash":run["config_hash"],
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


async def reconcile_research_failures(pool):
    rows=await pool.fetch("""SELECT DISTINCT ON (s.id)
      s.id AS shard_id,s.run_id,j.error,j.finished_at
      FROM research_shards s
      JOIN ml_jobs j ON j.dedupe_key=('strattester:'||s.id::text)
      WHERE s.status='queued' AND j.status='failed'
        AND NOT EXISTS(
          SELECT 1 FROM ml_jobs active
          WHERE active.dedupe_key=j.dedupe_key
            AND active.status IN ('queued','assigned','running'))
      ORDER BY s.id,j.finished_at DESC NULLS LAST,j.created_at DESC""")
    touched=set()
    for row in rows:
        changed=await pool.execute("""UPDATE research_shards
          SET status='failed',finished_at=now(),last_error=$2
          WHERE id=$1 AND status='queued'""",row["shard_id"],str(row["error"] or "compute job failed")[:4000])
        if changed.endswith(" 1"):touched.add(row["run_id"])
    while True:
        blocked=await pool.fetch("""SELECT DISTINCT s.id,s.run_id FROM research_shards s
          JOIN research_shard_dependencies d ON d.shard_id=s.id
          JOIN research_shards parent ON parent.id=d.depends_on_id
          WHERE s.status='queued' AND parent.status='failed'""")
        changed_any=False
        for row in blocked:
            changed=await pool.execute("""UPDATE research_shards
              SET status='failed',finished_at=now(),last_error='dependency failed'
              WHERE id=$1 AND status='queued'""",row["id"])
            if changed.endswith(" 1"):
                touched.add(row["run_id"]);changed_any=True
        if not changed_any:break
    for run_id in touched:
        counts=await pool.fetchrow("""SELECT count(*) FILTER(WHERE status='done') done,
          count(*) FILTER(WHERE status='failed') failed,
          count(*) FILTER(WHERE status NOT IN ('done','failed')) pending
          FROM research_shards WHERE run_id=$1""",run_id)
        if counts["pending"]==0 and counts["failed"]>0:
            await pool.execute("""UPDATE research_runs SET status='FAILED',finished_at=now(),
              last_error=COALESCE(last_error,'one or more research shards failed') WHERE id=$1""",run_id)
    return len(touched)


async def resolve_research_run_id(pool,reference):
    ref=str(reference or "").strip().lower()
    if len(ref)<8:
        raise ValueError("research run reference must contain at least 8 characters")
    rows=await pool.fetch("""SELECT id FROM research_runs
      WHERE lower(id::text) LIKE $1 ORDER BY created_at DESC LIMIT 2""",ref+"%")
    if not rows:raise ValueError("research run not found")
    if len(rows)>1:raise ValueError("research run reference is ambiguous")
    return rows[0]["id"]


async def cancel_research_run(pool,reference,reason="operator cancelled"):
    run_id=await resolve_research_run_id(pool,reference)
    async with pool.acquire() as c:
        async with c.transaction():
            run=await c.fetchrow("SELECT * FROM research_runs WHERE id=$1 FOR UPDATE",run_id)
            if not run:raise ValueError("research run not found")
            if str(run["status"]).upper() in ("COMPLETE","FAILED","CANCELLED"):
                return {"run_id":str(run_id),"status":str(run["status"]),"changed":False}
            text=str(reason)[:4000]
            await c.execute("""UPDATE research_runs SET status='CANCELLED',finished_at=now(),last_error=$2
              WHERE id=$1""",run_id,text)
            await c.execute("""UPDATE research_shards SET status='failed',finished_at=COALESCE(finished_at,now()),
              last_error=COALESCE(last_error,$2)
              WHERE run_id=$1 AND status<>'done'""",run_id,text)
            await c.execute("""UPDATE ml_jobs SET status='cancelled',finished_at=now(),lease_until=NULL,
              error=COALESCE(error,$2)
              WHERE dedupe_key IN (
                SELECT 'strattester:'||id::text FROM research_shards WHERE run_id=$1)
              AND status IN ('queued','assigned','running')""",run_id,text)
            await c.execute("""DELETE FROM ml_resource_reservations WHERE job_id IN (
              SELECT j.id FROM ml_jobs j JOIN research_shards s
                ON j.dedupe_key=('strattester:'||s.id::text)
              WHERE s.run_id=$1)""",run_id)
            return {"run_id":str(run_id),"status":"CANCELLED","changed":True}


async def finalize_research_run(pool,run_id):
    run=await pool.fetchrow("""SELECT * FROM research_runs
      WHERE id=$1 AND status='COMPLETE'""",run_id)
    if not run:return None
    if run["aggregate_fingerprint"] and run["result_artifact_id"]:
        return {"aggregate_fingerprint":run["aggregate_fingerprint"],
                "result_artifact_id":str(run["result_artifact_id"])}
    rows=await pool.fetch("""SELECT id,job_type,shard_key,result_manifest,result_hash
      FROM research_shards WHERE run_id=$1 ORDER BY shard_key,id""",run_id)
    if not rows or any(not r["result_manifest"] or not r["result_hash"] for r in rows):
        return None
    manifests=[dict(r["result_manifest"]) for r in rows]
    aggregate=aggregate_fingerprint(manifests)
    summary={
        "protocol_version":1,
        "run_id":str(run["id"]),
        "kind":str(run["kind"]),
        "dataset_id":str(run["dataset_id"]),
        "dataset_hash":str(run["dataset_hash"]),
        "config_hash":str(run["config_hash"]),
        "strattester_version":str(run["strattester_version"]),
        "aggregate_fingerprint":aggregate,
        "shards":[{
            "id":str(r["id"]),"shard_key":str(r["shard_key"]),
            "job_type":str(r["job_type"]),"result_hash":str(r["result_hash"])
        } for r in rows],
    }
    artifact=await publish_compute_bytes(pool,canonical_json(summary).encode("utf-8"),
        artifact_type="research_result",
        metadata={"run_id":str(run["id"]),"aggregate_fingerprint":aggregate},
        reusable=True)
    await pool.execute("""UPDATE research_runs SET aggregate_fingerprint=$2,result_artifact_id=$3
      WHERE id=$1 AND status='COMPLETE' AND result_artifact_id IS NULL""",
      run["id"],aggregate,uuid.UUID(str(artifact["id"])))
    return {"aggregate_fingerprint":aggregate,"result_artifact_id":str(artifact["id"]),
            "artifact_sha256":artifact["sha256"]}


async def finalize_completed_research_runs(pool,limit=50):
    rows=await pool.fetch("""SELECT id FROM research_runs
      WHERE status='COMPLETE' AND result_artifact_id IS NULL
      ORDER BY finished_at NULLS LAST,created_at LIMIT $1""",int(limit))
    finalized=0
    for row in rows:
        if await finalize_research_run(pool,row["id"]):finalized+=1
    return finalized


async def reconcile_research_runs(pool):
    await reconcile_research_failures(pool)
    await finalize_completed_research_runs(pool)
    rows=await pool.fetch("""SELECT id FROM research_runs
      WHERE status IN ('QUEUED','RUNNING') ORDER BY created_at""")
    created=0
    for row in rows:
        created+=await enqueue_research_shards(pool,row["id"])
    return created
