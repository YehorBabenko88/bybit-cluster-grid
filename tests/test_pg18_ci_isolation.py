"""Mocked provider proof tests. No Docker, SQL, host inspection or connection."""
import copy
import json
import pytest
from tools import ci_pg18 as ci


def environment(monkeypatch):
    for k,v in {'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux',
                'GITHUB_JOB':'pg18','GITHUB_REPOSITORY':'YehorBabenko88/bybit-cluster-grid',
                'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GRID_PG18_CONTAINER':'a'*64,
                'GRID_PG18_PORT':'49100','GRID_PG18_IMAGE_ID':'sha256:'+'b'*64}.items():
        monkeypatch.setenv(k,v)
    monkeypatch.delenv('DOCKER_HOST',raising=False)
    monkeypatch.delenv('DOCKER_CONTEXT',raising=False)


@pytest.mark.parametrize('key,value',[
    ('GITHUB_ACTIONS','false'),('RUNNER_ENVIRONMENT','self-hosted'),('RUNNER_OS','Windows'),
    ('GITHUB_JOB','other'),('GITHUB_REPOSITORY','other/repo'),('GITHUB_RUN_ID',''),
    ('GITHUB_RUN_ATTEMPT','0'),('DOCKER_HOST','tcp://example.invalid:1234'),
    ('DOCKER_CONTEXT','other')])
def test_untrusted_environment_never_calls_provider(monkeypatch,key,value):
    environment(monkeypatch)
    monkeypatch.setenv(key,value)
    def forbidden(*args):raise AssertionError('provider must not be called')
    monkeypatch.setattr(ci,'docker',forbidden)
    with pytest.raises(RuntimeError,match='HOSTED_CI_REQUIRED'):
        ci.attest()


def proof(monkeypatch):
    environment(monkeypatch)
    c={'Id':'a'*64,'Image':'sha256:'+'b'*64,'State':{'Running':True},
       'Config':{'Image':ci.IMAGE,'Labels':ci.labels(),
                 'Env':['PGDATA='+ci.PGDATA,'POSTGRES_USER=grid','POSTGRES_DB=grid']},
       'NetworkSettings':{'Ports':{'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'49100'}]}},
       'HostConfig':{'Binds':None,'Privileged':False,'Tmpfs':{ci.ROOT:'rw'}},'Mounts':[]}
    def docker(*args):
        if args[:2]==('context','inspect'):
            return json.dumps([{'Endpoints':{'docker':{'Host':'unix:///var/run/docker.sock'}}}])
        if args[0]=='inspect':return json.dumps([c])
        if args[-1]=='/proc/self/mountinfo':return '23 1 0:1 / '+ci.ROOT+' rw - tmpfs tmpfs rw'
        if args[-1]=='SHOW data_directory':return ci.PGDATA
        if args[-1]=='SHOW server_version_num':return '180004'
        if args[-1].startswith('SELECT system_identifier'):return '12345678'
        raise AssertionError('unexpected provider call')
    monkeypatch.setattr(ci,'docker',docker)
    return c


def test_complete_mock_proof(monkeypatch):
    proof(monkeypatch)
    assert ci.attest()=='12345678'


@pytest.mark.parametrize('attack',[
    'bind','privileged','wrong-image','wrong-image-id','wrong-run','stopped','wrong-data',
    'public-port','production-port','missing-tmpfs','rw-missing','nested-mount',
])
def test_bad_container_proof_blocks_before_host_sql(monkeypatch,attack):
    c=proof(monkeypatch)
    if attack=='bind':c['HostConfig']['Binds']=['/existing:/existing']
    elif attack=='privileged':c['HostConfig']['Privileged']=True
    elif attack=='wrong-image':c['Config']['Image']='postgres:16'
    elif attack=='wrong-image-id':c['Image']='sha256:wrong'
    elif attack=='wrong-run':c['Config']['Labels']['grid.audit.run_id']='1'
    elif attack=='stopped':c['State']['Running']=False
    elif attack=='wrong-data':c['Config']['Env'][0]='PGDATA=/installed'
    elif attack=='public-port':c['NetworkSettings']['Ports']['5432/tcp'][0]['HostIp']='0.0.0.0'
    elif attack=='production-port':monkeypatch.setenv('GRID_PG18_PORT','55433')
    elif attack=='missing-tmpfs':c['HostConfig']['Tmpfs']={}
    elif attack=='rw-missing':c['HostConfig']['Tmpfs'][ci.ROOT]='ro'
    elif attack=='nested-mount':c['Mounts']=[{'Type':'volume','Destination':ci.PGDATA}]
    with pytest.raises(RuntimeError,match='PROOF_REJECTED'):
        ci.attest()


def test_provider_failure_is_fail_closed(monkeypatch):
    environment(monkeypatch)
    def unavailable(*args):raise RuntimeError('unavailable')
    monkeypatch.setattr(ci,'docker',unavailable)
    with pytest.raises(RuntimeError):ci.attest()


def test_isolation_failure_never_connects_or_creates_database(monkeypatch):
    import asyncio
    import _pg18_database as fixture
    def denied():raise RuntimeError('proof denied')
    async def forbidden(*args,**kwargs):raise AssertionError('no installed PostgreSQL connection')
    monkeypatch.setattr(fixture,'attest',denied)
    monkeypatch.setattr(fixture.asyncpg,'connect',forbidden)
    async def run():
        with pytest.raises(RuntimeError,match='proof denied'):
            async with fixture.database():raise AssertionError('not entered')
    asyncio.run(run())


def test_provider_cannot_pull_or_run_before_local_daemon_proof(monkeypatch,tmp_path):
    environment(monkeypatch)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    monkeypatch.setenv('GITHUB_ENV',str(tmp_path/'github-env'))
    calls=[]
    def remote(*args):
        calls.append(args)
        if args==('context','inspect','default'):
            return json.dumps([{'Endpoints':{'docker':{'Host':'tcp://remote.invalid:2375'}}}])
        raise AssertionError('pull/run/stop before local daemon proof')
    monkeypatch.setattr(ci,'docker',remote)
    with pytest.raises(RuntimeError,match='LOCAL_DOCKER'):
        ci.start()
    assert calls==[('context','inspect','default')]
    assert not (tmp_path/'grid-pg18-ci.env').exists()
