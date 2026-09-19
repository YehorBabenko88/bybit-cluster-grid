import json,uuid

async def reconcile_lifecycle(pool):
    """Create only missing next-stage jobs. Unique logical keys make reconciliation restart-safe."""
    created=[]
    # READY datasets without a model get a training job.
    rows=await pool.fetch("""SELECT d.id FROM dataset_snapshots d
      WHERE d.status='READY' AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.dataset_id=d.id)""")
    for r in rows:
        if await _enqueue_once(pool,"train",{"dataset_id":str(r["id"])},f"train:{r['id']}"):
            created.append(("train",str(r["id"])))
    # Candidate stages advance only after explicit passed evaluation.
    stages=[("CANDIDATE","OOS","evaluate_oos"),("OOS_PASSED","ROBUSTNESS","robustness"),
            ("ROBUSTNESS_PASSED","SHADOW_START","shadow_start")]
    for status,stage,job_type in stages:
        rows=await pool.fetch("""SELECT id,dataset_id FROM model_registry WHERE status=$1""",status)
        for r in rows:
            if await _enqueue_once(pool,job_type,{"model_id":str(r["id"]),"dataset_id":str(r["dataset_id"])},
                                   f"{job_type}:{r['id']}"):
                created.append((job_type,str(r["id"])))
    return created

async def _enqueue_once(pool,job_type,payload,logical_key):
    job_id=uuid.uuid4()
    result=await pool.execute("""INSERT INTO ml_jobs(id,job_type,payload,status)
      SELECT $1,$2,$3::jsonb,'queued'
      WHERE NOT EXISTS(SELECT 1 FROM ml_jobs WHERE payload->>'logical_key'=$4
        AND status IN ('queued','assigned','running','done'))""",
      job_id,job_type,json.dumps({**payload,"logical_key":logical_key}),logical_key)
    return result.endswith(" 1")
