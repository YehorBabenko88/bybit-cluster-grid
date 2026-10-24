import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
import pytest
from installer.windows_preflight import validate_release, database_status, safe_failure, check_dependencies


@pytest.fixture(autouse=True)
def isolated_program_data(monkeypatch,tmp_path):
    monkeypatch.setenv('ProgramData',str(tmp_path/'programdata'))
    monkeypatch.setenv('PROGRAMDATA',str(tmp_path/'programdata'))


def test_manifest_hashes_and_rollback_protocol_files(tmp_path):
    files={'run_coordinator.py':'pass','grid/control_runtime.py':'pass','grid/collection_ownership.py':'pass','grid/retention.py':'pass'}
    for name,text in files.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    manifest={'version':'a'*40,'files':{name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}}
    (tmp_path/'release-manifest.json').write_text(json.dumps(manifest))
    assert validate_release(tmp_path,'a'*40)['status']=='PASS'
    (tmp_path/'grid/control_runtime.py').write_text('tampered')
    assert validate_release(tmp_path,'a'*40)['code']=='RELEASE_HASH_MISMATCH'


def test_manifest_cannot_escape_or_omit_python(tmp_path):
    (tmp_path/'release-manifest.json').write_text(json.dumps({'version':'a'*40,'files':{'../secret':'a'*64}}))
    assert validate_release(tmp_path,'a'*40)['status']=='BLOCKED'


def test_missing_db_tables_and_active_gate_fail_closed_without_ddl():
    class C:
        execute=AsyncMock()
        def transaction(self,**kw):
            assert kw=={'readonly':True}
            @asynccontextmanager
            async def tx():yield
            return tx()
        async def fetchval(self,sql,*args):
            if 'current_database' in sql:return 'bybit_cluster_grid'
            if 'to_regclass' in sql:return args[0]
            if 'state FROM grid_runtime_state' in sql:return 'ACTIVE'
        async def fetch(self,sql):
            from grid.migrations import MIGRATIONS
            return [{'version':v,'name':n} for v,n,_ in MIGRATIONS]
    c=C()
    result=asyncio.run(database_status(c,'bybit_cluster_grid'))
    assert result['code']=='RUNTIME_NOT_QUIESCENT'
    c.execute.assert_not_called()


def test_diagnostics_never_include_exception_text():
    result=safe_failure('DB_UNAVAILABLE',RuntimeError('postgresql://user:secret@host/db bot123'))
    assert result=={'status':'BLOCKED','code':'DB_UNAVAILABLE','error_type':'RuntimeError'}
    assert 'secret' not in json.dumps(result)


def test_dependency_failure_does_not_echo_child_output(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:type('R',(),{'returncode':1,'stdout':'secret','stderr':'password'})())
    assert 'secret' not in json.dumps(check_dependencies())
    assert check_dependencies()['code']=='DEPENDENCY_CHECK_FAILED'


def test_partial_retention_columns_are_not_accepted():
    class C:
        def transaction(self,**kw):
            @asynccontextmanager
            async def tx():yield
            return tx()
        async def fetchval(self,sql,*args):
            if 'current_database' in sql:return 'bybit_cluster_grid'
            if 'to_regclass' in sql:return args[0]
            return 'INFRA_ONLY'
        async def fetch(self,sql,*args):
            from grid.migrations import MIGRATIONS
            return [] if 'information_schema' in sql else [{'version':v,'name':n} for v,n,_ in MIGRATIONS]
    assert asyncio.run(database_status(C(),'bybit_cluster_grid'))['code']=='GRID_COLUMNS_INCOMPLETE'


@pytest.mark.parametrize('state,leader,code',[('INFRA_ONLY',True,'CONTROL_QUIESCENT_LEADER'),
    ('ACTIVE',True,'CONTROL_NOT_QUIESCENT'),('INFRA_ONLY',False,'CONTROL_NOT_LEADER')])
def test_smoke_is_get_only_does_not_follow_redirects_or_promote_gate(monkeypatch,state,leader,code):
    import aiohttp
    from installer.windows_preflight import smoke
    payload=json.dumps({'ok':True,'service':'Bybit Cluster Grid Coordinator','runtime_state':state,'control_leader':leader}).encode()
    class Reply:
        status=200;content_length=len(payload)
        content=type('Content',(),{'read':AsyncMock(return_value=payload)})()
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    class Session:
        def __init__(self,**kwargs):assert kwargs['trust_env'] is False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def get(self,url,**kwargs):
            assert url=='http://fixture/health'
            assert kwargs=={'allow_redirects':False}
            return Reply()
    monkeypatch.setattr(aiohttp,'ClientSession',Session)
    assert asyncio.run(smoke('http://fixture'))['code']==code


def test_cli_redacts_realistic_configuration_and_never_authorizes_activation(monkeypatch,tmp_path,capsys):
    import installer.windows_preflight as w
    secret='never-print-this-password'
    env=tmp_path/'protected.env'
    env.write_text('GRID_SHARED_TOKEN='+secret+'\nTELEGRAM_BOT_TOKEN='+secret+'\nPOSTGRES_DSN=postgresql://u:'+secret+'@localhost/db\n')
    monkeypatch.setattr(w,'check_dependencies',lambda:{'status':'PASS'})
    assert w.main(['--release-dir',str(tmp_path),'--expected-sha','a'*40,'--env-file',str(env)])==2
    output=capsys.readouterr().out
    assert secret not in output
    assert json.loads(output)['activation_authorized'] is False
    assert json.loads(output)['checks']['telegram']['code']=='TELEGRAM_CONFIGURED'


def test_schema_verification_failure_prevents_coordinator_services_and_tasks(monkeypatch):
    from grid import coordinator as c
    monkeypatch.setattr(c,'bootstrap_logging',lambda:None)
    monkeypatch.setattr(c,'install_asyncio_exception_filter',lambda loop:None)
    preparation=AsyncMock(side_effect=RuntimeError('injected schema contract failure'))
    monkeypatch.setattr(c,'prepare_database',preparation)
    def forbidden(*args):raise AssertionError('service created before schema verification')
    monkeypatch.setattr(c,'Storage',forbidden)
    monkeypatch.setattr(c,'ControlRuntime',forbidden)
    with pytest.raises(RuntimeError,match='injected schema contract failure'):
        asyncio.run(c.startup())
    preparation.assert_awaited_once()


@pytest.mark.parametrize('credential,expected',[('enrolled-secret','PASS'),('','BLOCKED'),(None,'BLOCKED')])
def test_file_only_enrolled_worker_credentials(monkeypatch,tmp_path,capsys,credential,expected):
    import installer.windows_preflight as w
    monkeypatch.delenv('NODE_CREDENTIAL',raising=False)
    env=tmp_path/'.env';env.write_text('RETENTION_ENABLED=false\n')
    if credential is not None:
        (tmp_path/'secrets').mkdir()
        (tmp_path/'secrets'/'node.credential').write_text(credential)
    monkeypatch.setattr(w,'check_dependencies',lambda:{'status':'PASS'})
    w.main(['--release-dir',str(tmp_path),'--expected-sha','a'*40,'--role','WORKER','--env-file',str(env)])
    output=capsys.readouterr().out
    assert 'enrolled-secret' not in output
    assert json.loads(output)['checks']['credentials']['status']==expected
