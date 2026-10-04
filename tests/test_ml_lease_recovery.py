import asyncio
from grid.ml_retry import recover_expired_ml_jobs

class Pool:
    def __init__(self,rows): self.rows=rows; self.calls=[]
    async def fetch(self,sql,*args): return self.rows
    async def execute(self,sql,*args):
        self.calls.append((sql,args)); return 'UPDATE 1' if sql.lstrip().startswith('UPDATE') else 'DELETE 1'

def test_expired_job_is_requeued():
    async def run():
        p=Pool([{'id':'j1','attempts':1,'max_attempts':3}])
        assert await recover_expired_ml_jobs(p)=={'recovered':1,'failed':0}
        assert any("status='queued'" in sql for sql,_ in p.calls)
    asyncio.run(run())

def test_exhausted_job_is_failed():
    async def run():
        p=Pool([{'id':'j1','attempts':3,'max_attempts':3}])
        assert await recover_expired_ml_jobs(p)=={'recovered':0,'failed':1}
        assert any("status='failed'" in sql for sql,_ in p.calls)
    asyncio.run(run())
