"""Real loopback heartbeat regression for the DB-less agent's replay sink."""
import asyncio
import contextlib

from aiohttp import web
from grid import worker as module


def test_dbless_worker_accepts_control_heartbeat_and_updates_storage_rate(monkeypatch,tmp_path):
    monkeypatch.setenv('ProgramData',str(tmp_path))
    monkeypatch.setenv('PROGRAMDATA',str(tmp_path))
    monkeypatch.setenv('GRID_CONTROL_JOURNAL',str(tmp_path/'journal.json'))
    monkeypatch.setenv('GRID_CONTROL_SNAPSHOTS',str(tmp_path/'snapshots'))
    monkeypatch.setattr(module,'snapshot',lambda:dict(node_id='loopback-worker',cpu_pct=0,ram_pct=0,disk_free=100*1024**3))
    monkeypatch.setattr(module,'internet_available',lambda:False)
    monkeypatch.setattr(module,'decommission_due',lambda *_:False)
    monkeypatch.setattr(module.settings,'heartbeat_seconds',.05)

    async def scenario():
        requests=[]
        async def heartbeat(request):
            requests.append(await request.json())
            return web.json_response(dict(runtime_state='INFRA_ONLY',market_work_enabled=False,
                symbols=[],micro_symbols=[],commands=[],recovery_profile=dict(minute_per_second=7.5,micro_per_second=12.5)))
        app=web.Application();app.router.add_post('/heartbeat',heartbeat)
        runner=web.AppRunner(app);await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        port=site._server.sockets[0].getsockname()[1]
        monkeypatch.setattr(module.settings,'coordinator_url','http://127.0.0.1:'+str(port))
        worker=module.Worker();assert worker.db is None
        task=asyncio.create_task(worker.heartbeat())
        try:
            until=asyncio.get_running_loop().time()+2
            while worker.last_assignment_heartbeat is None and asyncio.get_running_loop().time()<until:
                await asyncio.sleep(.02)
            assert requests,'actual loopback CONTROL request missing'
            assert worker.last_assignment_heartbeat is not None,'DB-less worker failed to renew its assignment lease'
            assert worker.storage.replay_rate==7.5
            assert worker.micro_storage.replay_rate==12.5
            assert worker.wanted==set(),'INFRA_ONLY must not start a market collector'
            assert worker.db is None,'agent must remain DB-less'
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await task
            await runner.cleanup()
    asyncio.run(scenario())
