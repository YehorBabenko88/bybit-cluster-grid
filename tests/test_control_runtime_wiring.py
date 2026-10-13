import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from grid import coordinator
from grid.control_runtime import FencedPool


def test_actual_startup_registers_services_with_election_before_any_start(monkeypatch):
    async def run():
        raw=object();db=SimpleNamespace(pool=raw)
        monkeypatch.setattr(coordinator,'db',None)
        monkeypatch.setattr(coordinator,'control_runtime',None)
        monkeypatch.setattr(coordinator,'prepare_database',AsyncMock(return_value=db))
        monkeypatch.setattr(coordinator,'bootstrap_logging',lambda:None)
        callbacks=[]
        class Runtime:
            def __init__(self,pool,start,stop):
                assert pool is raw
                callbacks.extend([start,stop])
            def start(self):callbacks.append('campaign')
        monkeypatch.setattr(coordinator,'ControlRuntime',Runtime)
        schema=AsyncMock()
        monkeypatch.setattr(coordinator,'ensure_instrument_schema',schema)
        await coordinator.startup()
        assert callbacks==[coordinator.start_leader_services,coordinator.stop_leader_services,'campaign']
        schema.assert_not_awaited()
        assert isinstance(db.pool,FencedPool)
    asyncio.run(run())


def test_follower_cannot_reach_control_handlers(monkeypatch):
    async def run():
        monkeypatch.setattr(coordinator,'control_runtime',None)
        mutation=AsyncMock()
        monkeypatch.setattr(coordinator,'enqueue_command',mutation)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=coordinator.app),base_url='http://synthetic') as client:
            result=await client.post('/nodes/worker/commands',json={'action':'start'})
        assert result.status_code==503
        mutation.assert_not_awaited()
    asyncio.run(run())
