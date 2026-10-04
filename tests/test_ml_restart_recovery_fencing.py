import asyncio
from contextlib import asynccontextmanager
from grid.ml_retry import recover_expired_ml_jobs


class Conn:
    def __init__(self):
        self.locked=False;self.execs=[]
    async def fetch(self,sql,*args):
        assert "FOR UPDATE SKIP LOCKED" in sql
        if self.locked:return []
        self.locked=True
        return [{"id":"job-1","attempts":1,"max_attempts":3}]
    async def execute(self,sql,*args):
        self.execs.append((sql,args));return "UPDATE 1"


class Pool:
    def __init__(self,conn):self.conn=conn
    @asynccontextmanager
    async def acquire(self):yield self.conn


class TxConn(Conn):
    @asynccontextmanager
    async def transaction(self):yield self


def test_restart_recovery_is_single_owner_and_releases_reservation():
    async def run():
        c=TxConn();p=Pool(c)
        first=await recover_expired_ml_jobs(p)
        second=await recover_expired_ml_jobs(p)
        assert first=={"recovered":1,"failed":0}
        assert second=={"recovered":0,"failed":0}
        assert any("DELETE FROM ml_resource_reservations" in sql for sql,_ in c.execs)
    asyncio.run(run())
