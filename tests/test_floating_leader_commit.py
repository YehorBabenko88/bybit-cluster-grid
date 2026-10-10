import asyncio
import pytest
from grid.floating_leader import FloatingLeader

class Tx:
    async def __aenter__(self):return self
    async def __aexit__(self,exc_type,exc,tb):
        if exc_type is None:raise RuntimeError("commit failed")

class Conn:
    def transaction(self):return Tx()
    async def fetchrow(self,*args):return None
    async def fetchval(self,*args):return 1

class Acquire:
    async def __aenter__(self):return Conn()
    async def __aexit__(self,*args):return None

class Pool:
    def acquire(self):return Acquire()

def test_commit_failure_never_exposes_leadership():
    async def scenario():
        leader=FloatingLeader(Pool(),node_id="node-a")
        with pytest.raises(RuntimeError,match="commit failed"):
            await leader.campaign()
        assert leader.is_leader is False
        assert leader.epoch is None
    asyncio.run(scenario())
