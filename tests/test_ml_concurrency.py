import asyncio
from grid.ml_concurrency import claim_ml_job,renew_ml_job,finish_ml_job
from grid.ml_worker_protocol import run_with_lease

class Conn:
    def __init__(self): self.claimed=False
    def transaction(self): return self
    async def __aenter__(self): return self
    async def __aexit__(self,*a): pass
    async def fetchrow(self,sql,*args):
        if sql.startswith("SELECT *"):
            if self.claimed:return None
            self.claimed=True; return {"id":"j1"}
        if sql.startswith("UPDATE ml_jobs"): return {"id":"j1","lease_owner":args[1],"lease_generation":1}
    async def execute(self,*a): return "UPDATE 1"
class Acquire:
    def __init__(self,c):self.c=c
    async def __aenter__(self):return self.c
    async def __aexit__(self,*a):pass
class Pool:
    def __init__(self):self.c=Conn()
    def acquire(self):return Acquire(self.c)
    async def execute(self,*a):return "UPDATE 1"

def test_claim_uses_transactional_single_owner_path():
    async def run():
        p=Pool()
        a=await claim_ml_job(p,"worker-a")
        b=await claim_ml_job(p,"worker-b")
        assert a["lease_owner"]=="worker-a" and b is None
        assert await renew_ml_job(p,"j1","worker-a",a["lease_generation"])
        assert await finish_ml_job(p,"j1","worker-a",a["lease_generation"])
    asyncio.run(run())


def test_lease_loss_cancels_running_workload():
    async def run():
        class LeasePool:
            def __init__(self): self.calls=0
            async def execute(self,sql,*args):
                if "UPDATE ml_jobs SET lease_until" in sql:
                    self.calls+=1
                    return "UPDATE 0"
                return "UPDATE 1"
        cancelled=asyncio.Event()
        async def work():
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()
        p=LeasePool()
        job={"id":"j1","lease_generation":7}
        try:
            await run_with_lease(p,job,"worker-a",work,lease_seconds=1,renew_every=.01)
            assert False,"lease loss should abort stale work"
        except RuntimeError as exc:
            assert "lease lost" in str(exc)
        assert cancelled.is_set()
        assert p.calls==1
    asyncio.run(run())


def test_expired_ml_recovery_uses_cooldown_before_reassignment():
    from pathlib import Path
    source=Path("grid/ml_orchestrator_service.py").read_text(encoding="utf-8")
    recover=source.split("async def recover(self):",1)[1].split("async def tick(self):",1)[0]
    assert "lease_until<now()" in recover
    assert "not_before=now()+interval '5 seconds'" in recover
    assert "attempts<max_attempts" in recover
    assert "attempts>=max_attempts" in recover


def test_lease_renew_database_error_cancels_running_workload():
    async def run():
        class BrokenLeasePool:
            async def execute(self,sql,*args):
                if "UPDATE ml_jobs SET lease_until" in sql:
                    raise ConnectionError("database unavailable")
                return "UPDATE 1"
        cancelled=asyncio.Event()
        async def work():
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()
        with __import__("pytest").raises(ConnectionError,match="database unavailable"):
            await run_with_lease(
                BrokenLeasePool(),{"id":"j2","lease_generation":3},
                "worker-a",work,lease_seconds=1,renew_every=.01
            )
        assert cancelled.is_set()
    asyncio.run(run())
