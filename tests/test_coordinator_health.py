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
