import asyncio
from grid.ml_concurrency import claim_ml_job,renew_ml_job,finish_ml_job

class Conn:
    def __init__(self): self.claimed=False
    def transaction(self): return self
    async def __aenter__(self): return self
    async def __aexit__(self,*a): pass
    async def fetchrow(self,sql,*args):
        if sql.startswith("SELECT *"):
            if self.claimed:return None
            self.claimed=True; return {"id":"j1"}
        if sql.startswith("UPDATE ml_jobs"): return {"id":"j1","lease_owner":args[1]}
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
        assert await renew_ml_job(p,"j1","worker-a")
        assert await finish_ml_job(p,"j1","worker-a")
    asyncio.run(run())
