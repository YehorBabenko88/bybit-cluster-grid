import asyncio
from contextlib import asynccontextmanager

from grid.strategy_runtime import StrategyContext


def test_strategy_fetch_uses_readonly_database_transaction():
    async def run():
        class Connection:
            readonly=False
            @asynccontextmanager
            async def transaction(self,readonly=False):
                self.readonly=readonly;yield
            async def fetch(self,*args):
                assert self.readonly is True
                return [{'n':1}]
        c=Connection()
        class Pool:
            @asynccontextmanager
            async def acquire(self):yield c
        assert await StrategyContext(Pool(),{}).fetch('SELECT 1')==[{'n':1}]
    asyncio.run(run())
