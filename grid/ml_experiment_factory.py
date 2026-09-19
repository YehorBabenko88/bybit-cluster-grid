import itertools,json,uuid

def expand_grid(grid):
    keys=sorted(grid)
    for values in itertools.product(*(grid[k] for k in keys)):
        yield dict(zip(keys,values))

async def create_experiment_jobs(pool,dataset_id,model_family,search_space,limit=32):
    ds=await pool.fetchrow("SELECT status,dataset_hash FROM dataset_snapshots WHERE id=$1",dataset_id)
    if not ds or ds["status"]!="READY": raise ValueError("experiment requires READY dataset")
    made=[]
    for hp in list(expand_grid(search_space))[:int(limit)]:
        logical="exp:"+str(dataset_id)+":"+model_family+":"+json.dumps(hp,sort_keys=True,separators=(",",":"))
        payload={"dataset_id":str(dataset_id),"model_family":model_family,"hyperparameters":hp,"logical_key":logical}
        jid=uuid.uuid4()
        r=await pool.execute("""INSERT INTO ml_jobs(id,job_type,payload,status,dedupe_key)
          VALUES($1,'train',$2::jsonb,'queued',$3) ON CONFLICT DO NOTHING""",
          jid,json.dumps(payload),logical)
        if r.endswith(" 1"):made.append(str(jid))
    return made
