import asyncio
from contextlib import asynccontextmanager
from grid.strattester_bridge import complete_strattester_job,renew_strattester_job


class Conn:
    def __init__(self):self.executed=[]
    @asynccontextmanager
    async def transaction(self):yield self
    async def fetchrow(self,sql,*args):
        # Simulates a stale worker: fenced SELECT cannot see the reassigned generation.
        if "FROM ml_jobs" in sql:return None
        raise AssertionError("stale completion must stop before touching research shard")
    async def execute(self,sql,*args):
        self.executed.append((sql,args));return "UPDATE 1"


class Pool:
    def __init__(self,renew="UPDATE 0"):self.conn=Conn();self.renew=renew
    @asynccontextmanager
    async def acquire(self):yield self.conn
    async def execute(self,sql,*args):return self.renew


def test_stale_strattester_generation_cannot_commit_after_reassignment():
    async def run():
        p=Pool()
        assert await complete_strattester_job(p,"job","node-a",1,{"irrelevant":"stale"}) is False
        assert p.conn.executed==[]
    asyncio.run(run())


def test_stale_strattester_generation_cannot_renew_after_reassignment():
    async def run():
        assert await renew_strattester_job(Pool(),"job","node-a",1) is False
    asyncio.run(run())
