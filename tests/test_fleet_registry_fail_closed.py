import asyncio
import pytest
from grid.fleet_control import _registered_targets, begin_fleet_delete, fleet_stop, fleet_resume

class RegistryUnavailable:
    def __init__(self):self.mutations=0
    async def execute(self,*args):self.mutations+=1
    async def fetch(self,*args):
        raise RuntimeError("credential registry unavailable")
    async def fetchrow(self,*args):return None

def test_registry_failure_does_not_silently_drop_offline_nodes():
    async def scenario():
        pool=RegistryUnavailable()
        with pytest.raises(RuntimeError,match="registry unavailable"):
            await _registered_targets(pool,{"online-node":{}})
    asyncio.run(scenario())

def test_fleet_delete_aborts_before_changing_global_runtime_gate(monkeypatch):
    async def scenario():
        pool=RegistryUnavailable()
        async def ensure(*args):return None
        async def latest(*args):return None
        async def runtime(*args):return {"state":"ACTIVE"}
        async def set_state(*args):
            raise AssertionError("global state must not change on registry failure")
        import grid.fleet_control as fleet
        monkeypatch.setattr(fleet,"ensure_fleet_schema",ensure)
        monkeypatch.setattr(fleet,"latest_operation",latest)
        monkeypatch.setattr(fleet,"set_runtime_state",set_state)
        with pytest.raises(RuntimeError,match="registry unavailable"):
            await begin_fleet_delete(pool,{"online-node":{}},"admin")
        assert pool.mutations==0
    asyncio.run(scenario())

def test_fleet_stop_aborts_without_scheduling_partial_commands(monkeypatch):
    async def scenario():
        pool=RegistryUnavailable()
        import grid.fleet_control as fleet
        async def ensure(*args):return None
        async def runtime(*args):return {"state":"ACTIVE"}
        monkeypatch.setattr(fleet,"ensure_fleet_schema",ensure)
        monkeypatch.setattr(fleet,"runtime_state",runtime)
        with pytest.raises(RuntimeError,match="registry unavailable"):
            await fleet_stop(pool,{"online-node":{}},"admin")
        assert pool.mutations==0
    asyncio.run(scenario())
