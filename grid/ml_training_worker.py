import json,uuid,hashlib
from .ml_splits import walk_forward


class StaleTrainingLease(RuntimeError):
    code="STALE_TRAINING_LEASE"


class TrainingWorker:
    """Reproducible training harness. Backends implement fit/predict/serialize."""
    def __init__(self,pool,backend,code_version):
        self.pool=pool; self.backend=backend; self.code_version=code_version

    async def _publish_candidate(self,mid,model_family,dataset_id,artifact,feature_version,
                                 hyperparameters,job_id=None,lease_owner=None,lease_generation=None):
        # Model publication is the commit point. When invoked from a leased ML job,
        # fence that commit inside the same DB transaction so an old worker cannot
        # publish after CONTROL has reassigned the job to another machine.
        if job_id is None:
            await self.pool.execute("""INSERT INTO model_registry
              (id,model_family,dataset_id,status,artifact_id,code_version,feature_version,hyperparameters)
              VALUES($1,$2,$3,'CANDIDATE',$4,$5,$6,$7::jsonb)""",
              mid,model_family,dataset_id,artifact,self.code_version,feature_version,
              json.dumps(hyperparameters or {}))
            return
        if lease_owner is None or lease_generation is None:
            raise ValueError("leased training publication requires owner and generation")
        async with self.pool.acquire() as c:
            async with c.transaction():
                current=await c.fetchrow("""SELECT id FROM ml_jobs WHERE id=$1 AND status='running'
                  AND lease_owner=$2 AND lease_generation=$3 AND lease_until>=now()
                  FOR UPDATE""",job_id,lease_owner,int(lease_generation))
                if not current:
                    raise StaleTrainingLease("ML lease lost before model publication")
                await c.execute("""INSERT INTO model_registry
                  (id,model_family,dataset_id,status,artifact_id,code_version,feature_version,hyperparameters)
                  VALUES($1,$2,$3,'CANDIDATE',$4,$5,$6,$7::jsonb)""",
                  mid,model_family,dataset_id,artifact,self.code_version,feature_version,
                  json.dumps(hyperparameters or {}))

    async def train(self,dataset_id,model_family="global",hyperparameters=None,
                    job_id=None,lease_owner=None,lease_generation=None):
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
        await self._publish_candidate(
            mid,model_family,dataset_id,artifact,ds["feature_version"],hyperparameters,
            job_id=job_id,lease_owner=lease_owner,lease_generation=lease_generation,
        )
        return {"model_id":str(mid),"fold_metrics":fold_metrics,"folds":len(folds)}
