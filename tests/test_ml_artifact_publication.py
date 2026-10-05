import asyncio
import uuid
import pytest
from grid.ml_training_worker import TrainingWorker,StaleTrainingLease


class Store:
    def __init__(self): self.saved=[]
    def put_bytes(self,data):
        aid=uuid.uuid4();self.saved.append((aid,bytes(data)))
        return {"id":aid,"storage_uri":"artifact://local/"+str(aid),
                "bytes":len(data),"sha256":"abc"}


class Pool:
    def __init__(self): self.execs=[]
    async def execute(self,sql,*args):
        self.execs.append((sql,args));return "INSERT 0 1"


class Backend: pass


def test_byte_artifact_is_registered_with_orphan_ttl_before_publication():
    async def run():
        p=Pool();s=Store();w=TrainingWorker(p,Backend(),"v1",s,orphan_ttl_minutes=15)
        aid=await w._persist_artifact(b"model","job",{"backend":"xgboost"})
        assert s.saved[0][0]==aid
        sql,args=p.execs[0]
        assert "INSERT INTO ml_artifacts" in sql
        assert args[0]==aid and args[1]=="job"
        assert args[2].startswith("artifact://local/")
        assert '"sha256": "abc"' in args[5]
    asyncio.run(run())


def test_published_artifact_is_made_reusable_and_ttl_free():
    async def run():
        p=Pool();w=TrainingWorker(p,Backend(),"v1")
        aid=uuid.uuid4()
        await w._make_artifact_reusable(aid)
        sql,args=p.execs[0]
        assert "reusable=true" in sql and "expires_at=NULL" in sql
        assert args==(aid,)
    asyncio.run(run())


def test_orphan_gc_contract_excludes_registered_models():
    from pathlib import Path
    gc=Path("grid/ml_artifact_gc.py").read_text(encoding="utf-8")
    assert "NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=a.id)" in gc
    worker=Path("grid/ml_training_worker.py").read_text(encoding="utf-8")
    assert worker.index("_persist_artifact(serialized") < worker.index("_publish_candidate(",
        worker.index("async def train"))
