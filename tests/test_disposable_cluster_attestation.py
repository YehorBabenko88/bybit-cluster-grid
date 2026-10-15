"""All Docker/PostgreSQL boundaries are mocked; no real service contacted."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import _postgres_test_database as db

ID='a'*64


def context(monkeypatch):
    for key,value in {'GRID_DISPOSABLE_POSTGRES_TESTS':'1','POSTGRES_DSN':'postgresql://grid:grid@127.0.0.1:5432/grid',
        'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux',
        'GITHUB_REPOSITORY':'YehorBabenko88/bybit-cluster-grid','GITHUB_RUN_ID':'12345',
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'python-preflight','GRID_TEST_POSTGRES_CONTAINER_ID':ID}.items():
        monkeypatch.setenv(key,value)
    monkeypatch.delenv('DOCKER_HOST',raising=False);monkeypatch.delenv('DOCKER_CONTEXT',raising=False)


def docker_result(args,**kwargs):
    assert kwargs['timeout']<=10
    assert args[:3]==['docker','--context','default']
    args=['docker']+args[3:]
    if args[1:3]==['context','inspect']:
        return SimpleNamespace(returncode=0,stdout=json.dumps([{'Endpoints':{'docker':{'Host':'unix:///var/run/docker.sock'}}}]))
    if args[1]=='inspect':
        item={'Id':ID,'State':{'Running':True},'Config':{'Image':'postgres:16','Env':['POSTGRES_DB=grid','POSTGRES_USER=grid','PGDATA=/var/lib/postgresql/data'],
                  'Labels':{'grid.audit.disposable':'1','grid.audit.run_id':'12345','grid.audit.run_attempt':'1',
                            'grid.audit.repository':'YehorBabenko88/bybit-cluster-grid'}},
              'HostConfig':{'Tmpfs':{'/var/lib/postgresql/data':'rw'}},
              'Mounts':[{'Type':'tmpfs','Destination':'/var/lib/postgresql/data'}],
              'NetworkSettings':{'Ports':{'5432/tcp':[{'HostIp':'0.0.0.0','HostPort':'5432'}]}}}
        return SimpleNamespace(returncode=0,stdout=json.dumps([item]))
    if args[1]=='exec' and args[-2:]==['cat','/proc/self/mountinfo']:
        return SimpleNamespace(returncode=0,stdout='25 1 0:30 / /var/lib/postgresql/data rw,nosuid,nodev - tmpfs tmpfs rw,size=65536k\\n'.replace('\\n','\n'))
    if args[1]=='exec' and args[-1]=='SHOW data_directory':return SimpleNamespace(returncode=0,stdout='/var/lib/postgresql/data\n')
    if args[1]=='exec':return SimpleNamespace(returncode=0,stdout='7654321098765432100\n')
    raise AssertionError(args)


@pytest.mark.parametrize('damage',['no-context','foreign-repository','self-hosted','missing-container',
    'installed-port','remote-docker','wrong-container','wrong-port','wrong-image','docker-error','persistent-data','wrong-run','missing-disposable-label','alternate-pgdata','nested-persistent-mount','effective-directory'])
def test_unattested_cluster_never_connects_or_creates(monkeypatch,damage):
    context(monkeypatch)
    if damage=='no-context':monkeypatch.delenv('GITHUB_ACTIONS')
    if damage=='foreign-repository':monkeypatch.setenv('GITHUB_REPOSITORY','foreign/repository')
    if damage=='self-hosted':monkeypatch.setenv('RUNNER_ENVIRONMENT','self-hosted')
    if damage=='missing-container':monkeypatch.delenv('GRID_TEST_POSTGRES_CONTAINER_ID')
    if damage=='installed-port':monkeypatch.setenv('POSTGRES_DSN','postgresql://grid:grid@127.0.0.1:55432/grid')
    if damage=='remote-docker':monkeypatch.setenv('DOCKER_HOST','tcp://remote:2375')
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if damage=='docker-error':raise TimeoutError('private provider detail')
        result=docker_result(args,**kwargs)
        if damage=='effective-directory' and args[-1]=='SHOW data_directory':result.stdout='/persistent/data\n'
        if args[3]=='inspect':
            data=json.loads(result.stdout)
            if damage=='alternate-pgdata':data[0]['Config']['Env'].append('PGDATA=/persistent/data')
            if damage=='nested-persistent-mount':data[0]['Mounts'].append({'Type':'bind','Destination':'/var/lib/postgresql/data/base'})
            if damage=='wrong-container':data[0]['Id']='b'*64
            if damage=='wrong-port':data[0]['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort']='5439'
            if damage=='wrong-image':data[0]['Config']['Image']='installed/postgres'
            if damage=='persistent-data':data[0]['HostConfig']['Tmpfs']={};data[0]['Mounts']=[{'Type':'volume','Destination':'/var/lib/postgresql/data'}]
            if damage=='wrong-run':data[0]['Config']['Labels']['grid.audit.run_id']='54321'
            if damage=='missing-disposable-label':data[0]['Config']['Labels'].pop('grid.audit.disposable')
            result.stdout=json.dumps(data)
        return result
    monkeypatch.setattr(db,'subprocess',SimpleNamespace(run=run),raising=False)
    connect=AsyncMock(side_effect=AssertionError('unattested connection attempted'))
    monkeypatch.setattr(db.asyncpg,'connect',connect)
    async def attempt():
        with pytest.raises(RuntimeError):
            async with db.disposable_database():raise AssertionError('yielded')
    asyncio.run(attempt());connect.assert_not_called()
    # The attestor may inspect kernel mounts before rejecting later metadata.
    # No rejected candidate may reach the host PostgreSQL connection.
    assert connect.await_count == 0


@pytest.mark.parametrize('server_id',['wrong-server','7654321098765432100'])
def test_create_requires_matching_cluster_id_readonly_probe(monkeypatch,server_id):
    context(monkeypatch)
    monkeypatch.setattr(db,'subprocess',SimpleNamespace(run=docker_result),raising=False)
    admin=SimpleNamespace(fetchval=AsyncMock(return_value=server_id),execute=AsyncMock(),close=AsyncMock())
    connect=AsyncMock(return_value=admin);pool=SimpleNamespace(close=AsyncMock())
    create_pool=AsyncMock(return_value=pool)
    monkeypatch.setattr(db.asyncpg,'connect',connect);monkeypatch.setattr(db.asyncpg,'create_pool',create_pool)
    async def attempt():
        if server_id=='wrong-server':
            with pytest.raises(RuntimeError,match='identity'):
                async with db.disposable_database():raise AssertionError('wrong cluster yielded')
        else:
            async with db.disposable_database() as actual:assert actual is pool
    asyncio.run(attempt())
    if server_id=='wrong-server':admin.execute.assert_not_called();create_pool.assert_not_called()
    else:
        assert admin.execute.call_args_list[1].args[0].startswith('CREATE DATABASE "grid_audit48_')
        assert connect.call_args.kwargs['server_settings']['default_transaction_read_only']=='on'
    admin.close.assert_awaited_once()
