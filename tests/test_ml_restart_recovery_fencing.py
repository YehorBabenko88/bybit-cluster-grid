import asyncio
from grid.ml_retry import recover_expired_ml_jobs


class Pool:
    def __init__(self):
        self.calls=0;self.execs=[]
    async def fetch(self,sql,*args):
        assert "FOR UPDATE SKIP LOCKED" in sql
        assert "UPDATE ml_jobs" in sql
        self.calls+=1
        return [{"id":"job-1","status":"queued"}] if self.calls==1 else []
    async def execute(self,sql,*args):
        self.execs.append((sql,args));return "DELETE 1"


def test_restart_recovery_is_single_owner_and_releases_reservation():
    async def run():
        p=Pool()
        first=await recover_expired_ml_jobs(p)
        second=await recover_expired_ml_jobs(p)
        assert first=={"recovered":1,"failed":0}
        assert second=={"recovered":0,"failed":0}
        assert sum("DELETE FROM ml_resource_reservations" in sql for sql,_ in p.execs)==1
    asyncio.run(run())
