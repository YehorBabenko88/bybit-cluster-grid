import asyncio
from contextlib import asynccontextmanager
from datetime import datetime,timezone,timedelta
from grid.archive_compute_queue import accept_archive_compute_result,renew_archive_compute_job


class Conn:
    def __init__(self,job,artifact=None):
        self.job=job;self.artifact=artifact or {}
        self.executed=[]
    @asynccontextmanager
    async def transaction(self):yield self
    async def fetchrow(self,sql,*args):
        if "FROM archive_compute_jobs" in sql:return self.job
        if "FROM ml_artifacts" in sql:return self.artifact
        return None
    async def fetchval(self,sql,*args):return True
    async def execute(self,sql,*args):
        self.executed.append((sql,args));return "UPDATE 1"


class Pool:
    def __init__(self,conn,renew_result="UPDATE 0"):self.conn=conn;self.renew_result=renew_result
    @asynccontextmanager
    async def acquire(self):yield self.conn
    async def execute(self,sql,*args):return self.renew_result


def _job(generation=2,status="running"):
    return {"id":"j","lease_owner":"node-b","lease_generation":generation,"status":status,
            "lease_until":datetime.now(timezone.utc)+timedelta(minutes=5),
            "symbol":"BTCUSDT","archive_date":datetime(2026,1,1).date(),
            "source_uri":"u","tick_size":0.5,"expected_sha256":None,"expected_bytes":None,
            "derived_artifact_id":"11111111-1111-1111-1111-111111111111","result_hash":None}


def _manifest():
    return {"symbol":"BTCUSDT","archive_date":"2026-01-01","source_uri":"u","tick_size":0.5,
            "source_sha256":"a"*64,"source_bytes":10,"source_rows":2,"derived_candles":1,
            "derived_artifact_id":"11111111-1111-1111-1111-111111111111",
            "derived_artifact_sha256":"b"*64,"derived_artifact_bytes":12}


def test_stale_archive_generation_cannot_commit_after_reassignment():
    async def run():
        c=Conn(_job(generation=2))
        p=Pool(c)
        assert await accept_archive_compute_result(p,"j","node-a",1,_manifest()) is False
        assert c.executed==[]
    asyncio.run(run())


def test_stale_archive_generation_cannot_renew_after_reassignment():
    async def run():
        assert await renew_archive_compute_job(Pool(Conn(_job()),"UPDATE 0"),"j","node-a",1) is False
    asyncio.run(run())
