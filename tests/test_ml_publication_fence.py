import asyncio
import pytest
from grid.ml_training_worker import TrainingWorker,StaleTrainingLease


class Tx:
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False


class Conn:
    def __init__(self,valid):
        self.valid=valid
        self.inserts=0
    def transaction(self): return Tx()
    async def fetchrow(self,sql,*args):
        if "FROM ml_jobs" in sql:
            return {"id":args[0]} if self.valid else None
        raise AssertionError(sql)
    async def execute(self,sql,*args):
        if "INSERT INTO model_registry" in sql:
            self.inserts+=1
            return "INSERT 0 1"
        raise AssertionError(sql)


class Acquire:
    def __init__(self,c): self.c=c
    async def __aenter__(self): return self.c
    async def __aexit__(self,*args): return False


class Pool:
    def __init__(self,valid):
        self.conn=Conn(valid)
    def acquire(self): return Acquire(self.conn)


class Backend: pass


def test_stale_generation_cannot_publish_candidate():
    async def run():
        p=Pool(False)
        w=TrainingWorker(p,Backend(),"test")
        with pytest.raises(StaleTrainingLease):
            await w._publish_candidate("model","global","dataset","artifact","v1",{},
                job_id="job",lease_owner="old-node",lease_generation=7)
        assert p.conn.inserts==0
    asyncio.run(run())


def test_current_generation_can_publish_candidate():
    async def run():
        p=Pool(True)
        w=TrainingWorker(p,Backend(),"test")
        await w._publish_candidate("model","global","dataset","artifact","v1",{},
            job_id="job",lease_owner="node-b",lease_generation=8)
        assert p.conn.inserts==1
    asyncio.run(run())


def test_publication_fence_is_in_same_transaction_as_registry_insert():
    from pathlib import Path
    s=Path("grid/ml_training_worker.py").read_text(encoding="utf-8")
    block=s.split("async def _publish_candidate",1)[1].split("async def train",1)[0]
    assert "async with c.transaction()" in block
    assert "lease_generation=$3" in block
    assert "lease_until>=now()" in block
    assert "FOR UPDATE" in block
