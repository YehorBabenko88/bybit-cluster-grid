import asyncio
from grid.scientific_method_registry import ScientificMethod,ScientificMethodRegistry


class Pool:
    def __init__(self):self.journaled=False
    async def fetchval(self,query,*args):
        if "SELECT status" in query:return "ENABLED"
        if "RETURNING failure_count" in query:return 1
    async def execute(self,query,*args):
        if "INSERT INTO scientific_method_errors" in query:self.journaled=True


def test_error_journal_survives_unusual_event_metadata():
    async def scenario():
        pool=Pool();registry=ScientificMethodRegistry()
        registry.register(ScientificMethod("bad","1",1,lambda event:1/0,{}))
        result=await registry.dispatch(pool,{"event_type":object(),"symbol":object()})
        assert result["bad"]["ok"] is False
        assert pool.journaled
    asyncio.run(scenario())
