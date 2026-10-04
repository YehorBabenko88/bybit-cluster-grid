import asyncio
from grid.ml_retry import recover_expired_ml_jobs

class Pool:
    def __init__(self,rows): self.rows=rows; self.calls=[]
    async def fetch(self,sql,*args):
        assert "FOR UPDATE SKIP LOCKED" in sql
        return self.rows
    async def execute(self,sql,*args):
        self.calls.append((sql,args)); return 'DELETE 1'

def test_expired_job_is_requeued():
    async def run():
        p=Pool([{'id':'j1','status':'queued'}])
        assert await recover_expired_ml_jobs(p)=={'recovered':1,'failed':0}
        assert any("ml_resource_reservations" in sql for sql,_ in p.calls)
    asyncio.run(run())

def test_exhausted_job_is_failed():
    async def run():
        p=Pool([{'id':'j1','status':'failed'}])
        assert await recover_expired_ml_jobs(p)=={'recovered':0,'failed':1}
        assert any("ml_resource_reservations" in sql for sql,_ in p.calls)
    asyncio.run(run())
