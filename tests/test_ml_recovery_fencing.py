import asyncio
from types import SimpleNamespace
from grid.ml_orchestrator_service import MLOrchestratorService, OBSERVING

class FakeConnection:
    def __init__(self,owner=True,still=True):
        self.owner=owner;self.still=still;self.writes=[];self.queries=[]
    async def execute(self,sql,*args):
        self.queries.append(sql)
        if "UPDATE ml_jobs" in sql or "DELETE FROM ml_resource_reservations" in sql:
            self.writes.append(sql)
        return "UPDATE 1"
    async def fetchval(self,sql,*args):
        self.queries.append(sql)
        if "FOR UPDATE" in sql:return 1 if self.owner else None
        if "lease_until>clock_timestamp()" in sql:return self.still
        raise AssertionError(sql)
    def transaction(self):return Context(self)

class Context:
    def __init__(self,value):self.value=value
    async def __aenter__(self):return self.value
    async def __aexit__(self,*args):return False

class Pool:
    def __init__(self,conn):self.conn=conn
    def acquire(self):return Context(self.conn)

def test_nonleader_recovery_must_not_mutate_jobs():
    async def scenario():
        c=FakeConnection(owner=False)
        svc=MLOrchestratorService(Pool(c),None,None)
        assert await svc.recover() is False
        assert not c.writes
        assert svc.state==OBSERVING
    asyncio.run(scenario())

def test_leader_recovery_checks_ownership_before_and_after_writes():
    async def scenario():
        c=FakeConnection()
        svc=MLOrchestratorService(Pool(c),None,None)
        assert await svc.recover() is True
        assert len(c.writes)==3
        assert "FOR UPDATE" in c.queries[1]
    asyncio.run(scenario())

def test_expired_leadership_rolls_back_recovery():
    async def scenario():
        c=FakeConnection(still=False)
        svc=MLOrchestratorService(Pool(c),None,None)
        try:
            await svc.recover()
        except RuntimeError as e:
            assert "leadership expired" in str(e)
        else:
            raise AssertionError("expected leadership fence")
    asyncio.run(scenario())
