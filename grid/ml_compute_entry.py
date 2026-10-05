import argparse,asyncio,json,os,sys,traceback
from .config import settings
from .db import Database
from .ml_artifact_store import LocalArtifactStore
from .ml_boost_backend import TabularBoostBackend
from .ml_training_worker import TrainingWorker


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


async def main_async(job_json):
    job=json.loads(job_json)
    if job.get("job_type")!="train":raise ValueError("unsupported compute job type")
    result=await train_job(job)
    print(json.dumps(result,separators=(",",":")))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--job-json",required=True)
    a=p.parse_args()
    asyncio.run(main_async(a.job_json))


if __name__=="__main__":
    main()
