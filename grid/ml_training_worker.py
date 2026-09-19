import json,uuid
from .ml_splits import walk_forward

class TrainingWorker:
    """Reproducible training harness. Backends implement fit/predict/serialize."""
    def __init__(self,pool,backend,code_version):
        self.pool=pool; self.backend=backend; self.code_version=code_version

    async def train(self,dataset_id,model_family="global",hyperparameters=None):
        ds=await self.pool.fetchrow("""SELECT * FROM dataset_snapshots
          WHERE id=$1 AND status='READY'""",dataset_id)
        if not ds: raise ValueError("dataset is not READY")
        rows=await self.pool.fetch("""SELECT s.* FROM dataset_samples d
          JOIN ml_event_samples s ON s.sample_id=d.sample_id
          WHERE d.dataset_id=$1 ORDER BY d.ordinal""",dataset_id)
        folds=walk_forward([dict(r) for r in rows])
        if not folds: raise ValueError("not enough samples for walk-forward training")
        fold_metrics=[]
        for train,valid in folds:
            model=self.backend.fit(train,hyperparameters or {})
            pred=self.backend.predict(model,valid)
            fold_metrics.append(self.backend.evaluate(valid,pred))
        final=self.backend.fit([dict(r) for r in rows],hyperparameters or {})
        artifact=await self.backend.serialize(final)
        mid=uuid.uuid4()
        await self.pool.execute("""INSERT INTO model_registry
          (id,model_family,dataset_id,status,artifact_id,code_version,feature_version,hyperparameters)
          VALUES($1,$2,$3,'CANDIDATE',$4,$5,$6,$7::jsonb)""",
          mid,model_family,dataset_id,artifact,self.code_version,ds["feature_version"],
          json.dumps(hyperparameters or {}))
        return {"model_id":str(mid),"fold_metrics":fold_metrics,"folds":len(folds)}
