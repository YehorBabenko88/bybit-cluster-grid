import argparse,asyncio,json,os,sys,traceback
from .config import settings
from .db import Database
from .ml_artifact_store import LocalArtifactStore
from .ml_boost_backend import TabularBoostBackend
from .ml_training_worker import TrainingWorker
from .ml_splits import walk_forward
from pathlib import Path


async def train_job(job):
    payload=dict(job["payload"] or {})
    backend_name=str(payload.get("backend","xgboost")).lower()
    if backend_name not in ("xgboost","lightgbm"):
        raise ValueError("unsupported ML backend")
    dataset_id=payload.get("dataset_id")
    if not dataset_id:raise ValueError("train job requires dataset_id")
    hp=dict(payload.get("hyperparameters") or {})
    # Resource controls are not model hyperparameters and cannot inject commands.
    threads=max(1,min(int(payload.get("threads",1)),int(os.cpu_count() or 1)))
    db=Database();await db.connect()
    try:
        worker=TrainingWorker(
            db.pool,TabularBoostBackend(backend_name,threads=threads,
              seed=int(payload.get("seed",1729))),
            code_version=str(payload.get("code_version","grid")),
            artifact_store=LocalArtifactStore(settings.ml_artifact_root))
        return await worker.train(
            dataset_id,model_family=str(payload.get("model_family","global")),
            hyperparameters=hp,job_id=job["id"],
            lease_owner=job["lease_owner"],lease_generation=job["lease_generation"])
    finally:
        await db.close()


async def train_bundle(bundle_path,artifact_path,result_path):
    bundle=json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    job=bundle["job"];dataset=bundle["dataset"]
    if job.get("job_type")!="train":raise ValueError("unsupported compute job type")
    payload=dict(job.get("payload") or {})
    backend_name=str(payload.get("backend","xgboost")).lower()
    if backend_name not in ("xgboost","lightgbm"):raise ValueError("unsupported ML backend")
    hp=dict(payload.get("hyperparameters") or {})
    rows=list(dataset.get("samples") or [])
    if not rows:raise ValueError("dataset has no samples")
    threads=max(1,min(int(payload.get("threads",1)),int(os.cpu_count() or 1)))
    backend=TabularBoostBackend(backend_name,threads=threads,seed=int(payload.get("seed",1729)))
    folds=walk_forward(rows)
    if not folds:raise ValueError("not enough samples for walk-forward training")
    fold_metrics=[]
    for train,valid in folds:
        fold_model=backend.fit(train,hp)
        pred=backend.predict(fold_model,valid)
        fold_metrics.append(backend.evaluate(valid,pred,target_key=hp.get("target_key")))
    # Validation is strictly out-of-sample. Only after evaluation do we fit the
    # deployable artifact on the complete immutable dataset.
    model=backend.fit(rows,hp)
    artifact=await backend.serialize(model)
    metrics={"validation":"walk_forward","folds":len(folds),"fold_metrics":fold_metrics}
    Path(artifact_path).write_bytes(artifact)
    Path(result_path).write_text(json.dumps({"metrics":metrics},separators=(",",":")),encoding="utf-8")
    return {"metrics":metrics}

async def main_async(job_json):
    job=json.loads(job_json)
    if job.get("job_type")!="train":raise ValueError("unsupported compute job type")
    result=await train_job(job)
    print(json.dumps(result,separators=(",",":")))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--job-json")
    p.add_argument("--bundle");p.add_argument("--artifact");p.add_argument("--result")
    a=p.parse_args()
    if a.bundle or a.artifact or a.result:
        if not (a.bundle and a.artifact and a.result):raise SystemExit("bundle mode requires --bundle --artifact --result")
        asyncio.run(train_bundle(a.bundle,a.artifact,a.result))
    elif a.job_json:
        asyncio.run(main_async(a.job_json))
    else:
        raise SystemExit("job mode requires --job-json")


if __name__=="__main__":
    main()
