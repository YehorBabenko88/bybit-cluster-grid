import asyncio
from unittest.mock import patch
from grid.floating_leader import FloatingLeader

class Tx:
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False

class Conn:
    def __init__(self,epoch): self.epoch=epoch;self.args=None
    def transaction(self): return Tx()
    async def fetchrow(self,*args):
        return {"owner":"other-node","lease_until":None,"metadata":{"epoch":self.epoch}}
    async def execute(self,*args): self.args=args;return "INSERT 0 1"

class Acquire:
    def __init__(self,conn):self.conn=conn
    async def __aenter__(self):return self.conn
    async def __aexit__(self,*args):return False

class Pool:
    def __init__(self,conn):self.conn=conn
    def acquire(self):return Acquire(self.conn)

def test_epoch_never_reuses_previous_epoch_when_clock_moves_backwards():
    async def scenario():
        conn=Conn(9999999999999)
        leader=FloatingLeader(Pool(conn),node_id="new-node")
        with patch("grid.floating_leader.time.time",return_value=1):
            assert await leader.campaign()
        assert leader.epoch==10000000000000
        assert conn.args[-1]==leader.epoch
    asyncio.run(scenario())

def test_renew_lost_lease_clears_epoch():
    class RenewPool:
        async def execute(self,*args):return "UPDATE 0"
    async def scenario():
        leader=FloatingLeader(RenewPool(),node_id="node")
        leader.is_leader=True;leader.epoch=42
        assert not await leader.renew()
        assert leader.epoch is None
    asyncio.run(scenario())
