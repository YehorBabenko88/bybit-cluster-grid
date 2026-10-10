import json,uuid,hashlib
from datetime import datetime,timezone,timedelta
from collections.abc import Mapping
from .ml_splits import walk_forward


def _json_object(value):
    """Decode default asyncpg JSONB strings and reject non-object payloads."""
    if isinstance(value,str):
        value=json.loads(value)
    if not isinstance(value,Mapping):
        raise ValueError("JSON payload must be an object")
    return dict(value)


class StaleTrainingLease(RuntimeError):
    code="STALE_TRAINING_LEASE"


class TrainingWorker:
    """Reproducible training harness. Backends implement fit/predict/serialize."""
    def __init__(self,pool,backend,code_version,artifact_store=None,orphan_ttl_minutes=60):
        self.pool=pool; self.backend=backend; self.code_version=code_version
        self.artifact_store=artifact_store
        self.orphan_ttl_minutes=max(1,int(orphan_ttl_minutes))

    async def _persist_artifact(self,data,job_id=None,metadata=None):
        # Legacy backends may already return a database artifact UUID.
        if not isinstance(data,(bytes,bytearray,memoryview)):
            return data
        if self.artifact_store is None:
            raise RuntimeError("byte-producing ML backend requires an artifact store")
        saved=self.artifact_store.put_bytes(bytes(data))
        expires=datetime.now(timezone.utc)+timedelta(minutes=self.orphan_ttl_minutes)
        await self.pool.execute("""INSERT INTO ml_artifacts
          (id,artifact_type,owner_job,storage_uri,bytes,status,reusable,expires_at,metadata)
          VALUES($1,'MODEL',$2,$3,$4,'ACTIVE',false,$5,$6::jsonb)""",
          saved["id"],job_id,saved["storage_uri"],saved["bytes"],expires,
          json.dumps(dict(metadata or {},sha256=saved["sha256"])))
        return saved["id"]

    async def _make_artifact_reusable(self,artifact_id):
        await self.pool.execute("""UPDATE ml_artifacts SET reusable=true,expires_at=NULL,last_used_at=now()
          WHERE id=$1 AND status='ACTIVE'""",artifact_id)

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
            obj=_json_object(r["payload"])
            raw=json.dumps(obj,sort_keys=True,default=str,separators=(",",":"))
            h=hashlib.sha256(raw.encode()).hexdigest()
            if h!=r["payload_hash"]: raise ValueError("immutable dataset payload hash mismatch")
            hashes.append(h); rows.append(obj)
        aggregate=hashlib.sha256("\n".join(hashes).encode()).hexdigest()
        if aggregate!=ds["dataset_hash"]: raise ValueError("dataset aggregate hash mismatch")
        folds=walk_forward(rows)
        if not folds: raise ValueError("not enough samples for walk-forward training")
        fold_metrics=[]
        for train,valid in folds:
            model=self.backend.fit(train,hyperparameters or {})
            pred=self.backend.predict(model,valid)
            try:
                metric=self.backend.evaluate(valid,pred,target_key=(hyperparameters or {}).get("target_key"))
            except TypeError:
                metric=self.backend.evaluate(valid,pred)
            fold_metrics.append(metric)
        final=self.backend.fit(rows,hyperparameters or {})
        serialized=await self.backend.serialize(final)
        artifact=await self._persist_artifact(serialized,job_id,{
            "model_family":model_family,"dataset_id":str(dataset_id),
            "code_version":self.code_version,"feature_version":ds["feature_version"],
            "lease_generation":lease_generation,
        })
        mid=uuid.uuid4()
        await self._publish_candidate(
            mid,model_family,dataset_id,artifact,ds["feature_version"],hyperparameters,
            job_id=job_id,lease_owner=lease_owner,lease_generation=lease_generation,
        )
        # Publication succeeded, so this artifact is now reachable from model_registry
        # and must no longer be eligible for orphan TTL collection.
        if isinstance(serialized,(bytes,bytearray,memoryview)):
            await self._make_artifact_reusable(artifact)
        return {"model_id":str(mid),"artifact_id":str(artifact),
                "fold_metrics":fold_metrics,"folds":len(folds)}
