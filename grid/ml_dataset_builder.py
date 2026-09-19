import hashlib,json,uuid
from datetime import datetime,timezone

class DatasetBuilder:
    """Build immutable manifests from target-ready, quality-approved samples."""
    def __init__(self,pool,feature_version="1"):
        self.pool=pool; self.feature_version=feature_version

    async def build(self,purpose,owner,cutoff_ts,criteria=None):
        criteria=criteria or {}; did=uuid.uuid4()
        await self.pool.execute("""INSERT INTO dataset_snapshots
          (id,purpose,cutoff_ts,created_by,criteria,status,feature_version)
          VALUES($1,$2,$3,$4,$5::jsonb,'BUILDING',$6)""",
          did,purpose,cutoff_ts,owner,json.dumps(criteria),self.feature_version)
        try:
            rows=await self.pool.fetch("""SELECT sample_id,symbol,event_ts,feature_ts,features,
              instrument_features,target,quality_status,split_group FROM ml_event_samples
              WHERE target_ready=true AND quality_status='GOOD' AND event_ts<=$1
                AND feature_ts<event_ts ORDER BY event_ts,sample_id""",cutoff_ts)
            manifest=[_canonical(r) for r in rows if _matches(r,criteria)]
            if not manifest: raise ValueError("dataset has no eligible samples")
            digest=hashlib.sha256("\n".join(manifest).encode()).hexdigest()
            async with self.pool.acquire() as c:
                async with c.transaction():
                    await c.executemany("INSERT INTO dataset_samples(dataset_id,sample_id,ordinal) VALUES($1,$2,$3)",
                        [(did,r["sample_id"],i) for i,r in enumerate(rows) if _matches(r,criteria)])
            await self.pool.execute("""UPDATE dataset_snapshots SET dataset_hash=$2,
              sample_count=$3,status='READY' WHERE id=$1 AND status='BUILDING'""",
              did,digest,len(manifest))
            return {"id":str(did),"dataset_hash":digest,"sample_count":len(manifest),
                    "cutoff_ts":cutoff_ts,"feature_version":self.feature_version}
        except Exception:
            await self.pool.execute("UPDATE dataset_snapshots SET status='FAILED' WHERE id=$1",did)
            raise

def _canonical(r):
    d={k:r[k] for k in ("sample_id","symbol","event_ts","feature_ts","features",
                         "instrument_features","target","quality_status","split_group")}
    return json.dumps(d,sort_keys=True,default=str,separators=(",",":"))

def _matches(r,c):
    symbols=c.get("symbols")
    return not symbols or r["symbol"] in symbols
