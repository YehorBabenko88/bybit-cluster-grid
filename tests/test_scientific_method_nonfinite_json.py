import asyncio
from grid.scientific_method_registry import ScientificMethod,ScientificMethodRegistry


class Pool:
    def __init__(self):self.queries=[];self.failures=0
    async def fetchval(self,query,*args):
        if "SELECT status" in query:return "ENABLED"
        if "RETURNING failure_count" in query:
            self.failures+=1
            return self.failures
    async def execute(self,query,*args):
        self.queries.append(query)


def test_nonfinite_plugin_observation_is_isolated_and_not_inserted():
    async def scenario():
        pool=Pool();registry=ScientificMethodRegistry()
        registry.register(ScientificMethod("invalid","1",1,lambda event:{"score":float("nan")},{}))
        result=await registry.dispatch(pool,{"source_event_id":7,"event_type":"trade"})
        assert not result["invalid"]["ok"]
        assert pool.failures==1
        assert not any("INSERT INTO scientific_method_events" in q for q in pool.queries)
        assert any("INSERT INTO scientific_method_errors" in q for q in pool.queries)
    asyncio.run(scenario())
