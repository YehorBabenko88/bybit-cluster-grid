import json,uuid,hashlib

VARIANTS=("BASE","REGIME","MARKOV","REGIME_MARKOV","ML","ML_MARKOV")

def comparison_key(dataset_id,strategy_name,variant,config):
    raw=json.dumps({"dataset":str(dataset_id),"strategy":strategy_name,"variant":variant,
                    "config":config},sort_keys=True,separators=(",",":"))
    return "cmp:"+hashlib.sha256(raw.encode()).hexdigest()

async def create_comparison_jobs(pool,dataset_id,strategy_name,config=None,variants=VARIANTS):
    config=config or {}
    ds=await pool.fetchrow("SELECT status,dataset_hash FROM dataset_snapshots WHERE id=$1",dataset_id)
    if not ds or ds["status"]!="READY":raise ValueError("comparison requires READY immutable dataset")
    made=[]
    for variant in variants:
        key=comparison_key(dataset_id,strategy_name,variant,config)
        payload={"dataset_id":str(dataset_id),"dataset_hash":ds["dataset_hash"],
                 "strategy_name":strategy_name,"variant":variant,"config":config,
                 "comparison_group":f"{dataset_id}:{strategy_name}"}
        jid=uuid.uuid4()
        r=await pool.execute("""INSERT INTO ml_jobs(id,job_type,payload,status,dedupe_key)
          VALUES($1,'strategy_compare',$2::jsonb,'queued',$3) ON CONFLICT DO NOTHING""",
          jid,json.dumps(payload),key)
        if r.endswith(" 1"):made.append({"job_id":str(jid),"variant":variant})
    return made
