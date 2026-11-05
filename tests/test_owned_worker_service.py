import asyncio
import hashlib
import shutil
import subprocess
import time

import aiohttp
from aiohttp import web
from grid import coordinator, worker


def test_owned_worker_health_real_binding_and_control(monkeypatch,tmp_path):
    from grid.owned_worker_service import OwnedWorkerService
    root=tmp_path/'source';root.mkdir()
    (root/'owned.txt').write_bytes(b'owned\n')
    git=shutil.which('git')
    def run(*args):
        return subprocess.check_output([git,'-C',str(root),*args]).decode().strip()
    run('init');run('config','user.name','Owned test');run('config','user.email','owned@example.invalid')
    run('add','.');run('commit','-m','fixture')
    identity=('grid','1.2.3','lab-release','a'*64,run('rev-parse','HEAD'))
    for key,value in zip(coordinator._OWNED_MODULE_ENV,identity):monkeypatch.setenv(key,value)
    monkeypatch.setenv('UNIFIED_GIT_EXECUTABLE',git)
    monkeypatch.setenv('UNIFIED_GIT_SHA256',hashlib.sha256(open(git,'rb').read()).hexdigest())
    monkeypatch.setattr(coordinator,'_MODULE_SOURCE_ROOT',root)
    for key in ('ProgramData','PROGRAMDATA'):monkeypatch.setenv(key,str(tmp_path))
    monkeypatch.setenv('GRID_CONTROL_JOURNAL',str(tmp_path/'journal.json'))
    monkeypatch.setenv('GRID_CONTROL_SNAPSHOTS',str(tmp_path/'snapshots'))
    monkeypatch.setattr(worker.settings,'role','worker')
    monkeypatch.setattr(worker.settings,'heartbeat_seconds',.05)
    monkeypatch.setattr(worker.settings,'grid_shared_token','fixture-control')
    monkeypatch.setattr(worker,'node_credential',lambda:'fixture-node')
    monkeypatch.setattr(worker,'snapshot',lambda:dict(node_id='PC1',cpu_pct=0,ram_pct=0,disk_free=100*1024**3))
    monkeypatch.setattr(worker,'internet_available',lambda:False)
    monkeypatch.setattr(worker,'decommission_due',lambda *_:False)
    monkeypatch.setattr(worker,'ml_runtime_ready',lambda:False)
    async def scenario():
        allow=asyncio.Event();requests=[]
        async def heartbeat(request):
            assert request.headers['X-Grid-Token']=='fixture-control'
            assert request.headers['X-Node-Credential']=='fixture-node'
            requests.append(await request.json())
            if not allow.is_set():return web.Response(status=403)
            return web.json_response(dict(runtime_state='INFRA_ONLY',market_work_enabled=False,symbols=[],commands=[]))
        app=web.Application();app.router.add_post('/heartbeat',heartbeat)
        control=web.AppRunner(app);await control.setup()
        site=web.TCPSite(control,'127.0.0.1',0);await site.start()
        monkeypatch.setattr(worker.settings,'coordinator_url','http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]))
        service=OwnedWorkerService();await service.start(0)
        url='http://127.0.0.1:'+str(service.port)+'/internal/v2/module/health'
        headers={'Authorization':'Bearer '+identity[3]}
        try:
            async with aiohttp.ClientSession() as client:
                async def probe(status,ready):
                    async with client.get(url,headers=headers) as response:
                        assert response.status==status
                        body=await response.json();assert body['ready'] is ready
                        assert body['instance_token']==identity[3]
                await probe(503,False)
                allow.set()
                async with asyncio.timeout(4):
                    while service.worker.last_assignment_heartbeat is None:await asyncio.sleep(.02)
                await probe(200,True)
                assert requests and service.worker.db is None and not service.worker.wanted
                for method,suffix,extra in [('GET','?q=1',{}),('POST','',{}),('GET','',{'Origin':'http://foreign.invalid'}),('GET','',{'Host':'foreign.invalid'})]:
                    async with client.request(method,url+suffix,headers={**headers,**extra}) as response:assert response.status in (400,403,405)
                async with client.get(url,headers=[('Authorization',headers['Authorization']),('Authorization',headers['Authorization'])]) as response:assert response.status==403
                allow.clear();service.worker.last_assignment_heartbeat=time.monotonic()-2
                await probe(503,False)
                service.task.cancel();await asyncio.gather(service.task,return_exceptions=True)
                await probe(503,False)
        finally:
            await service.close();await control.cleanup()
        (root/'owned.txt').write_bytes(b'tampered\n')
        failed=OwnedWorkerService()
        try:
            await failed.start(0)
        except RuntimeError:pass
        else:raise AssertionError('dirty source accepted')
        assert failed.task is None
    asyncio.run(scenario())


def test_default_invocation_is_inert(monkeypatch):
    from grid.owned_worker_service import main
    monkeypatch.delenv('UNIFIED_MODULE_ID',raising=False)
    assert main([])==0
