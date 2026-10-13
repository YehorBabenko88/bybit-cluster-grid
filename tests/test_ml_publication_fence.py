import asyncio
import pytest
from grid.ml_training_worker import TrainingWorker,StaleTrainingLease


class Tx:
    def __init__(self,c):self.c=c
    async def __aenter__(self):self.c.in_transaction=True;return self
    async def __aexit__(self,*args):self.c.in_transaction=False;return False


class Conn:
    def __init__(self,valid):
        self.valid=valid
        self.inserts=0
        self.in_transaction=False
        self.clock_checks=0
    def transaction(self): return Tx(self)
    async def fetchval(self,sql,*args):
        assert self.in_transaction
        assert 'clock_timestamp()' in sql
        self.clock_checks+=1
        return 5 if self.valid else None
    async def fetchrow(self,sql,*args):
        if "FROM ml_jobs" in sql:
            return {"id":args[0]} if self.valid else None
        raise AssertionError(sql)
    async def execute(self,sql,*args):
        if "INSERT INTO model_registry" in sql:
            assert self.in_transaction
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
        assert p.conn.clock_checks==2
    asyncio.run(run())


def test_expired_after_row_lock_is_rejected():
    async def run():
        p=Pool(True)
        async def expired(*args):return None
        p.conn.fetchval=expired
        with pytest.raises(StaleTrainingLease):
            await TrainingWorker(p,Backend(),'test')._publish_candidate(
                'model','global','dataset','artifact','v1',{},job_id='job',
                lease_owner='node',lease_generation=1)
        assert p.conn.inserts==0
    asyncio.run(run())
