import hashlib,json,uuid

class DatasetBuilder:
    """Build immutable manifests without materializing the full dataset in RAM."""
    def __init__(self,pool,feature_version="1",batch_size=500):
        self.pool=pool; self.feature_version=feature_version; self.batch_size=max(50,int(batch_size))

    async def build(self,purpose,owner,cutoff_ts,criteria=None):
        criteria=criteria or {}; did=uuid.uuid4()
        await self.pool.execute("""INSERT INTO dataset_snapshots
          (id,purpose,cutoff_ts,created_by,criteria,status,feature_version)
          VALUES($1,$2,$3,$4,$5::jsonb,'BUILDING',$6)""",
          did,purpose,cutoff_ts,owner,json.dumps(criteria),self.feature_version)
        count=0; digest=hashlib.sha256()
        try:
            async with self.pool.acquire() as c:
                async with c.transaction():
                    cursor=c.cursor("""SELECT sample_id,symbol,event_ts,feature_ts,features,
                      instrument_features,target,quality_status,split_group,label_end_ts
                      FROM ml_event_samples
                      WHERE target_ready=true AND quality_status='GOOD' AND event_ts<=$1
                        AND label_end_ts IS NOT NULL AND label_end_ts<=$1
                        AND feature_ts<event_ts ORDER BY event_ts,sample_id""",cutoff_ts,
                      prefetch=self.batch_size)
                    members=[];payloads=[]
                    async for r in cursor:
                        if not _matches(r,criteria):continue
                        manifest=_canonical(r)
                        payload_hash=hashlib.sha256(manifest.encode()).hexdigest()
                        if count: digest.update(b"\n")
                        digest.update(payload_hash.encode())
                        members.append((did,r["sample_id"],count))
                        payloads.append((did,r["sample_id"],count,manifest,payload_hash,r["event_ts"],
                                         r["feature_ts"],_get(r,"label_end_ts"),_get(r,"split_group")))
                        count+=1
                        if len(members)>=self.batch_size:
                            await _flush(c,members,payloads);members=[];payloads=[]
                    if members:await _flush(c,members,payloads)
                    if not count:raise ValueError("dataset has no eligible samples")
                    await c.execute("""UPDATE dataset_snapshots SET dataset_hash=$2,
                      sample_count=$3,status='READY' WHERE id=$1 AND status='BUILDING'""",
                      did,digest.hexdigest(),count)
            return {"id":str(did),"dataset_hash":digest.hexdigest(),"sample_count":count,
                    "cutoff_ts":cutoff_ts,"feature_version":self.feature_version}
        except Exception:
            await self.pool.execute("UPDATE dataset_snapshots SET status='FAILED' WHERE id=$1",did)
            raise

async def _flush(c,members,payloads):
    await c.executemany("INSERT INTO dataset_samples(dataset_id,sample_id,ordinal) VALUES($1,$2,$3)",members)
    await c.executemany("""INSERT INTO dataset_sample_payloads
      (dataset_id,sample_id,ordinal,payload,payload_hash,event_ts,feature_ts,label_end_ts,split_group)
      VALUES($1,$2,$3,$4::jsonb,$5,$6,$7,$8,$9)""",payloads)

def _get(r,key,default=None):
    try:return r[key]
    except (KeyError,TypeError):return default

def _canonical(r):
    d={k:_get(r,k) for k in ("sample_id","symbol","event_ts","feature_ts","features",
                         "instrument_features","target","quality_status","split_group","label_end_ts")}
    d["sample_id"]=_get(r,"sample_id"); d["symbol"]=_get(r,"symbol"); d["event_ts"]=_get(r,"event_ts"); d["feature_ts"]=_get(r,"feature_ts")
    return json.dumps(d,sort_keys=True,default=str,separators=(",",":"))

def _matches(r,c):
    symbols=c.get("symbols")
    return not symbols or r["symbol"] in symbols
