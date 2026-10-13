import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock


def test_coordinator_exposes_health_endpoint(monkeypatch):
    from grid import coordinator
    async def run():
        raw=SimpleNamespace(fetchval=AsyncMock(return_value=1))
        monkeypatch.setattr(coordinator,'db',SimpleNamespace(pool=object(),raw_pool=raw))
        monkeypatch.setattr(coordinator,'control_runtime',None)
        monkeypatch.setattr(coordinator,'runtime_state',AsyncMock(return_value={'state':'STOPPED'}))
        result=await coordinator.health()
        assert result['ok'] is True
        assert result['control_leader'] is False
        assert result['runtime_state']=='STOPPED'
        raw.fetchval.assert_awaited_once_with('SELECT 1')
    asyncio.run(run())


def test_health_does_not_report_epoch_lost_during_database_probe(monkeypatch):
    from grid import coordinator
    from grid.control_runtime import Epoch
    async def run():
        token=Epoch('old',1);runtime=SimpleNamespace(ready=True,token=token)
        async def read(sql,*args):
            if 'EXISTS' in sql:
                token.active=False;runtime.ready=False;runtime.token=None
            return True
        monkeypatch.setattr(coordinator,'db',SimpleNamespace(pool=object(),raw_pool=SimpleNamespace(fetchval=read)))
        monkeypatch.setattr(coordinator,'control_runtime',runtime)
        monkeypatch.setattr(coordinator,'runtime_state',AsyncMock(return_value={'state':'ACTIVE'}))
        result=await coordinator.health()
        assert result['control_leader'] is False
        assert result['control_owner'] is None and result['control_epoch'] is None
    asyncio.run(run())
