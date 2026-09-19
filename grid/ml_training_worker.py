import json,uuid,hashlib
from .ml_splits import walk_forward

class TrainingWorker:
    """Reproducible training harness. Backends implement fit/predict/serialize."""
    def __init__(self,pool,backend,code_version):
        self.pool=pool; self.backend=backend; self.code_version=code_version

    async def train(self,dataset_id,model_family="global",hyperparameters=None):
        ds=await self.pool.fetchrow("""SELECT * FROM dataset_snapshots
          WHERE id=$1 AND status='READY'""",dataset_id)
        if not ds: raise ValueError("dataset is not READY")
        frozen=await self.pool.fetch("""SELECT ordinal,payload,payload_hash FROM dataset_sample_payloads
          WHERE dataset_id=$1 ORDER BY ordinal""",dataset_id)
        if len(frozen)!=ds["sample_count"]: raise ValueError("immutable dataset payload count mismatch")
        hashes=[]; rows=[]
        for r in frozen:
            raw=json.dumps(r["payload"],sort_keys=True,default=str,separators=(",",":"))
            h=hashlib.sha256(raw.encode()).hexdigest()
            if h!=r["payload_hash"]: raise ValueError("immutable dataset payload hash mismatch")
            hashes.append(h); rows.append(dict(r["payload"]))
        aggregate=hashlib.sha256("\n".join(hashes).encode()).hexdigest()
        if aggregate!=ds["dataset_hash"]: raise ValueError("dataset aggregate hash mismatch")
        folds=walk_forward(rows)
        if not folds: raise ValueError("not enough samples for walk-forward training")
        fold_metrics=[]
        for train,valid in folds:
            model=self.backend.fit(train,hyperparameters or {})
            pred=self.backend.predict(model,valid)
            fold_metrics.append(self.backend.evaluate(valid,pred))
        final=self.backend.fit(rows,hyperparameters or {})
        artifact=await self.backend.serialize(final)
        mid=uuid.uuid4()
        await self.pool.execute("""INSERT INTO model_registry
          (id,model_family,dataset_id,status,artifact_id,code_version,feature_version,hyperparameters)
          VALUES($1,$2,$3,'CANDIDATE',$4,$5,$6,$7::jsonb)""",
          mid,model_family,dataset_id,artifact,self.code_version,ds["feature_version"],
          json.dumps(hyperparameters or {}))
        return {"model_id":str(mid),"fold_metrics":fold_metrics,"folds":len(folds)}
