import asyncio
from datetime import datetime, timedelta, timezone
from grid.floating_leader import FloatingLeader

class Tx:
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False

class Conn:
    def __init__(self,owner):self.owner=owner;self.writes=0
    def transaction(self):return Tx()
    async def fetchrow(self,*args):
        return {"owner":self.owner,"lease_until":datetime.now(timezone.utc)+timedelta(minutes=1),"metadata":{"epoch":12}}
    async def fetchval(self,*args):return datetime.now(timezone.utc)
    async def execute(self,*args):self.writes+=1

class Acquire:
    def __init__(self,c):self.c=c
    async def __aenter__(self):return self.c
    async def __aexit__(self,*args):return False

class Pool:
    def __init__(self,c):self.c=c
    def acquire(self):return Acquire(self.c)

def test_same_node_cannot_take_unexpired_lease():
    async def scenario():
        conn=Conn("CONTROL")
        candidate=FloatingLeader(Pool(conn),node_id="CONTROL")
        assert not await candidate.campaign()
        assert not candidate.is_leader
        assert candidate.epoch is None
        assert conn.writes==0
    asyncio.run(scenario())

def test_other_node_cannot_take_unexpired_lease():
    async def scenario():
        conn=Conn("CONTROL")
        candidate=FloatingLeader(Pool(conn),node_id="OTHER")
        assert not await candidate.campaign()
        assert conn.writes==0
    asyncio.run(scenario())
