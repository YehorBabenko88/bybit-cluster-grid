import asyncio
from contextlib import asynccontextmanager
import pytest
from grid.retention_v2 import cleanup_dataset_safe

class FakeConnection:
    def __init__(self,required):
        self.calls=0
        self.required=required
    @asynccontextmanager
    async def transaction(self):
        yield self
    async def fetchval(self,*args):
        return self.required
    async def execute(self,sql,*args):
        if sql.startswith("LOCK TABLE"):
            return "LOCK TABLE"
        self.calls+=1
        return "DELETE "+str(args[1])

class Acquire:
    def __init__(self,c):self.c=c
    async def __aenter__(self):return self.c
    async def __aexit__(self,*args):pass

class Pool:
    def __init__(self,required=1):
        self.required=required
        self.conn=FakeConnection(required)
    async def fetchval(self,*args):return self.required
    def acquire(self):return Acquire(self.conn)

def test_retention_is_bounded_even_when_every_batch_is_full():
    async def scenario():
        pool=Pool()
        removed=await cleanup_dataset_safe(pool,"market_events",7,batch_size=3,max_batches=4)
        assert removed==12
        assert pool.conn.calls==4
    asyncio.run(scenario())

@pytest.mark.parametrize("days,batch,batches",[(-1,100,1),(7,0,1),(7,100,0)])
def test_retention_rejects_unsafe_limits_before_database_access(days,batch,batches):
    async def scenario():
        with pytest.raises(ValueError):
            await cleanup_dataset_safe(Pool(), "market_events",days,batch,batches)
    asyncio.run(scenario())

def test_retention_preserves_data_without_required_consumers():
    async def scenario():
        pool=Pool(required=0)
        assert await cleanup_dataset_safe(pool,"market_events",7,max_batches=2)==0
        assert pool.conn.calls==0
    asyncio.run(scenario())
