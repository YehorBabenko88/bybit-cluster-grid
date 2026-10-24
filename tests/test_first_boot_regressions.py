"""Unit reproductions; these are not the real hosted end-to-end run."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest


def test_db_less_worker_applies_recovery_rates_without_database(monkeypatch,tmp_path):
    from grid import worker as module
    monkeypatch.setenv('ProgramData',str(tmp_path))
    monkeypatch.setenv('PROGRAMDATA',str(tmp_path))
    monkeypatch.setattr(module,'snapshot',lambda:dict(node_id='unit-node',cpu_pct=0,ram_pct=0,disk_free=100*1024**3))
    monkeypatch.setattr(module,'mark_coordinator_success',lambda:None)
    monkeypatch.setattr(module,'internet_available',lambda:False)
    monkeypatch.setattr(module,'decommission_due',lambda *a:False)
    monkeypatch.setattr(module,'active_control_url',AsyncMock(return_value='http://127.0.0.1:1'))
    class Response:
        status=200
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def json(self):return dict(runtime_state='INFRA_ONLY',market_work_enabled=False,recovery_profile=dict(minute_per_second=3,micro_per_second=7))
    class Session:
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        def post(self,*a,**kw):return Response()
    monkeypatch.setattr(module.aiohttp,'ClientSession',Session)
    async def run():
        w=module.Worker();w.restart_requested=True
        try:
            assert w.db is None
            await w.heartbeat()
            assert w.storage.replay_rate==3 and w.micro_storage.replay_rate==7
        finally:
            w.storage.spool.close();w.micro_storage.spool.close()
    asyncio.run(run())


def test_default_reachability_uses_configured_rest_endpoint(monkeypatch):
    from grid import resilience
    from grid.config import settings
    calls=[]
    monkeypatch.setattr(settings,'bybit_rest_url','http://127.0.0.1:17891')
    monkeypatch.setattr(resilience,'_probe_tcp',lambda *a:calls.append(a))
    asyncio.run(resilience.wait_for_internet())
    assert calls==[('127.0.0.1',17891,3)]


@pytest.mark.parametrize('url',['file:///tmp/x','https://user:secret@example.invalid','https://','http://127.0.0.1:0'])
def test_invalid_reachability_endpoint_does_not_probe(monkeypatch,url):
    from grid import resilience
    from grid.config import settings
    monkeypatch.setattr(settings,'bybit_rest_url',url)
    monkeypatch.setattr(resilience,'_probe_tcp',lambda *a:pytest.fail('unexpected probe'))
    with pytest.raises(ValueError):asyncio.run(resilience.wait_for_internet())


def test_cleanup_admin_reconnect_requires_fresh_cluster_attestation(monkeypatch):
    from tests import _pg18_database as fixture
    calls=[]
    monkeypatch.setattr(fixture,'attest',lambda:(_ for _ in ()).throw(RuntimeError('proof failed')))
    connect=AsyncMock();monkeypatch.setattr(fixture.asyncpg,'connect',connect)
    with pytest.raises(RuntimeError):asyncio.run(fixture.cleanup_admin(SimpleNamespace(is_closed=lambda:True),{},'expected'))
    connect.assert_not_called()


def test_cleanup_admin_does_not_adopt_a_replaced_cluster(monkeypatch):
    from tests import _pg18_database as fixture
    monkeypatch.setattr(fixture,'attest',lambda:'foreign')
    connect=AsyncMock();monkeypatch.setattr(fixture.asyncpg,'connect',connect)
    with pytest.raises(RuntimeError):asyncio.run(fixture.cleanup_admin(SimpleNamespace(is_closed=lambda:True),{},'expected'))
    connect.assert_not_called()


def test_provider_creation_receipt_survives_later_inspect_failure(monkeypatch,tmp_path):
    from tools import ci_pg18
    monkeypatch.setattr(ci_pg18,'hosted',lambda:None)
    monkeypatch.setattr(ci_pg18,'local_daemon',lambda:None)
    monkeypatch.setattr(ci_pg18.secrets,'token_hex',lambda n:'0'*64)  # explicit non-secret unit fixture
    monkeypatch.setattr(ci_pg18,'labels',lambda:{})
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path));monkeypatch.setenv('GITHUB_ENV',str(tmp_path/'github-env'))
    def docker(*args):
        if args[0]=='run':return 'a'*64
        if args[0]=='inspect':raise RuntimeError('injected inspect failure')
        return ''
    monkeypatch.setattr(ci_pg18,'docker',docker)
    with pytest.raises(RuntimeError):ci_pg18.start()
    receipt=tmp_path/'github-env'
    assert receipt.is_file() and 'GRID_PG18_CONTAINER='+'a'*64 in receipt.read_text()


def test_shutdown_pipe_failure_still_contains_owned_process():
    from integration.first_boot_process import OwnedChild
    child=object.__new__(OwnedChild)
    child.env={'ROLE':'coordinator'};child.same_process=lambda:True
    class Process:
        returncode=None
        stdin=SimpleNamespace(close=lambda:None)
        def send_signal(self,value):self.returncode=-15
        async def wait(self):return self.returncode
    child.process=Process();child.command=AsyncMock(side_effect=RuntimeError('pipe failed'))
    async def run():
        child.reader=asyncio.create_task(asyncio.sleep(0))
        with pytest.raises(RuntimeError,match='COOPERATIVE_SHUTDOWN_FAILED'):await child.stop()
        assert child.process.returncode is not None
    asyncio.run(run())


def test_teardown_attempts_every_child_before_raising():
    from integration.first_boot_process import stop_all
    bad=SimpleNamespace(process=SimpleNamespace(returncode=None),stop=AsyncMock(side_effect=RuntimeError('failure')))
    good=SimpleNamespace(process=SimpleNamespace(returncode=None),stop=AsyncMock())
    with pytest.raises(RuntimeError,match='CHILD_CONTAINMENT_FAILED'):asyncio.run(stop_all([good,bad]))
    good.stop.assert_awaited_once();bad.stop.assert_awaited_once()


def test_registration_rejects_stale_session_and_heartbeat():
    from integration.first_boot import registration_is_fresh
    old={'a':dict(collector_session='old',last_seen=100,integrity_ok=True)}
    assert not registration_is_fresh(old,old,{'a'})
    assert not registration_is_fresh({'a':dict(collector_session='new',last_seen=100,integrity_ok=True)},old,{'a'})
    assert registration_is_fresh({'a':dict(collector_session='new',last_seen=101,integrity_ok=True)},old,{'a'})
