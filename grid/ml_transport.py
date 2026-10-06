import hashlib,json,uuid
from .ml_worker_protocol import accept_assigned_job,renew_running_job,complete_running_job,fail_running_job
from .ml_artifact_store import LocalArtifactStore
from .ml_training_worker import TrainingWorker


def _public_job(row):
    d=dict(row)
    allowed=("id","job_type","payload","lease_owner","lease_generation","lease_until","attempts")
    out={k:d.get(k) for k in allowed}
    for k,v in list(out.items()):
        if hasattr(v,"isoformat"):out[k]=v.isoformat()
        elif isinstance(v,uuid.UUID):out[k]=str(v)
    return out


async def claim(pool,node_id):
    row=await accept_assigned_job(pool,node_id)
    return _public_job(row) if row else None


async def renew(pool,job_id,node_id,generation):
    return await renew_running_job(pool,job_id,node_id,int(generation))


async def dataset_page(pool,job_id,node_id,generation,offset=0,limit=500):
    job=await pool.fetchrow("""SELECT payload FROM ml_jobs WHERE id=$1 AND lease_owner=$2
      AND lease_generation=$3 AND status='running' AND lease_until>=now()""",
      job_id,node_id,int(generation))
    if not job:return None
    payload=dict(job["payload"] or {})
    did=payload.get("dataset_id")
    if not did:raise ValueError("train job requires dataset_id")
    ds=await pool.fetchrow("""SELECT id,dataset_hash,feature_version,sample_count FROM dataset_snapshots
      WHERE id=$1 AND status='READY'""",did)
    if not ds:raise ValueError("dataset is not READY")
    offset=max(0,int(offset));limit=max(1,min(1000,int(limit)))
    rows=await pool.fetch("""SELECT ordinal,payload,payload_hash FROM dataset_sample_payloads
      WHERE dataset_id=$1 ORDER BY ordinal OFFSET $2 LIMIT $3""",did,offset,limit)
    samples=[]
    for r in rows:
        raw=r["payload"];obj=json.loads(raw) if isinstance(raw,str) else dict(raw)
        canonical=json.dumps(obj,sort_keys=True,default=str,separators=(",",":"))
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        if digest!=r["payload_hash"]:raise RuntimeError("dataset payload hash mismatch")
        samples.append({"ordinal":int(r["ordinal"]),"payload":obj,"payload_hash":digest})
    return {"dataset_id":str(ds["id"]),"dataset_hash":ds["dataset_hash"],
            "feature_version":ds["feature_version"],"sample_count":int(ds["sample_count"]),
            "offset":offset,"limit":limit,"samples":samples}

async def dataset_bundle(pool,job_id,node_id,generation):
    first=await dataset_page(pool,job_id,node_id,generation,0,1000)
    if first is None:return None
    samples=[];hashes=[];offset=0
    while offset<first["sample_count"]:
        page=first if offset==0 else await dataset_page(pool,job_id,node_id,generation,offset,1000)
        for item in page["samples"]:
            samples.append(item["payload"]);hashes.append(item["payload_hash"])
        offset+=len(page["samples"])
        if not page["samples"]:break
    digest=hashlib.sha256("\n".join(hashes).encode()).hexdigest()
    if digest!=first["dataset_hash"]:raise RuntimeError("dataset manifest hash mismatch")
    return {"dataset_id":first["dataset_id"],"dataset_hash":digest,
            "feature_version":first["feature_version"],"sample_count":len(samples),"samples":samples}


async def register_saved_artifact(pool,job_id,node_id,generation,saved,metadata=None):
    row=await pool.fetchrow("""SELECT payload FROM ml_jobs WHERE id=$1 AND lease_owner=$2
      AND lease_generation=$3 AND status='running' AND lease_until>=now() FOR UPDATE""",
      job_id,node_id,int(generation))
    if not row:return None
    artifact_id=saved["id"]
    await pool.execute("""INSERT INTO ml_artifacts
      (id,artifact_type,owner_job,storage_uri,bytes,status,reusable,expires_at,metadata)
      VALUES($1,'MODEL',$2,$3,$4,'ACTIVE',false,now()+interval '1 hour',$5::jsonb)""",
      artifact_id,job_id,saved["storage_uri"],saved["bytes"],
      json.dumps(dict(metadata or {},sha256=saved["sha256"])))
    return {"artifact_id":str(artifact_id),"sha256":saved["sha256"]}


async def publish_artifact(pool,store,job_id,node_id,generation,data,sha256,metadata=None):
    row=await pool.fetchrow("""SELECT payload FROM ml_jobs WHERE id=$1 AND lease_owner=$2
      AND lease_generation=$3 AND status='running' AND lease_until>=now() FOR UPDATE""",
      job_id,node_id,int(generation))
    if not row:return None
    actual=hashlib.sha256(data).hexdigest()
    if actual!=str(sha256):raise ValueError("artifact sha256 mismatch")
    saved=store.put_bytes(data)
    return await register_saved_artifact(pool,job_id,node_id,generation,saved,metadata)


async def finalize_model(pool,job_id,node_id,generation,artifact_id,metrics=None):
    row=await pool.fetchrow("""SELECT payload FROM ml_jobs WHERE id=$1 AND lease_owner=$2
      AND lease_generation=$3 AND status='running' AND lease_until>=now() FOR UPDATE""",
      job_id,node_id,int(generation))
    if not row:return False
    p=dict(row["payload"] or {})
    did=p.get("dataset_id")
    ds=await pool.fetchrow("SELECT feature_version FROM dataset_snapshots WHERE id=$1 AND status='READY'",did)
    if not ds:raise ValueError("dataset is not READY")
    model_id=uuid.uuid4()
    async with pool.acquire() as c:
        async with c.transaction():
            locked=await c.fetchrow("""SELECT 1 FROM ml_jobs WHERE id=$1 AND lease_owner=$2
              AND lease_generation=$3 AND status='running' AND lease_until>=now() FOR UPDATE""",
              job_id,node_id,int(generation))
            if not locked:return False
            art=await c.fetchrow("""SELECT id FROM ml_artifacts WHERE id=$1 AND owner_job=$2
              AND status='ACTIVE' FOR UPDATE""",artifact_id,job_id)
            if not art:return False
            await c.execute("""INSERT INTO model_registry
              (id,model_family,dataset_id,artifact_id,feature_version,code_version,hyperparameters,status)
              VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,'CANDIDATE')""",
              model_id,str(p.get("model_family","global")),did,artifact_id,ds["feature_version"],
              str(p.get("code_version","grid")),json.dumps(p.get("hyperparameters") or {}))
            await c.execute("""INSERT INTO model_evaluations
              (id,model_id,stage,dataset_id,metrics,passed,evaluator_version)
              VALUES($1,$2,'TRAIN',$3,$4::jsonb,false,$5)""",
              uuid.uuid4(),model_id,did,json.dumps(metrics or {}),"agent-train-v1")
            await c.execute("""UPDATE ml_artifacts SET reusable=true,expires_at=NULL,last_used_at=now()
              WHERE id=$1""",artifact_id)
            ok=await c.execute("""UPDATE ml_jobs SET status='done',finished_at=now(),lease_until=NULL
              WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3 AND status='running'""",
              job_id,node_id,int(generation))
            if not ok.endswith(" 1"):raise RuntimeError("lease lost during model commit")
            await c.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",job_id)
    return {"model_id":str(model_id)}
