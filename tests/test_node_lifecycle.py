import asyncio
from datetime import datetime,timezone,timedelta
import pytest
from grid.node_lifecycle import record_node_seen,node_may_compute


class FakePool:
    def __init__(self,state=None):self.state=state;self.executed=[]
    async def fetchrow(self,sql,*args):
        if "SELECT state" in sql:return {"state":self.state} if self.state else None
    async def fetchval(self,sql,*args):
        if "SELECT state" in sql:return self.state
    async def execute(self,sql,*args):
        self.executed.append((sql,args))
        if "INSERT INTO node_lifecycle" in sql:self.state="ONLINE"
        return "UPDATE 1"


def test_decommissioned_node_cannot_revive_on_heartbeat():
    async def run():
        p=FakePool("DECOMMISSIONED")
        assert await record_node_seen(p,"n1")=="DECOMMISSIONED"
        assert p.executed==[]
        assert await node_may_compute(p,"n1") is False
    asyncio.run(run())


def test_offline_node_heartbeat_returns_online():
    async def run():
        p=FakePool("OFFLINE")
        assert await record_node_seen(p,"n1")=="ONLINE"
        assert p.state=="ONLINE"
    asyncio.run(run())
