"""Disposable PostgreSQL 18 CI provider. Not an operator/physical deployment tool."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

IMAGE = 'postgres:18.4'
ROOT = '/var/lib/postgresql'
PGDATA = ROOT + '/18/docker'


def hosted():
    expected = {'GITHUB_ACTIONS':'true', 'RUNNER_ENVIRONMENT':'github-hosted',
                'RUNNER_OS':'Linux', 'GITHUB_JOB':'pg18',
                'GITHUB_REPOSITORY':'YehorBabenko88/bybit-cluster-grid'}
    if (any(os.environ.get(k) != v for k,v in expected.items())
            or any(not re.fullmatch(r'[1-9][0-9]*', os.environ.get(k,''))
                   for k in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))
            or os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT')):
        raise RuntimeError('PG18_HOSTED_CI_REQUIRED_BEFORE_ANY_PROVIDER_OR_SQL_OPERATION')


def docker(*args):
    result = subprocess.run(['docker','--context','default',*args], capture_output=True,
                            text=True, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError('PG18_PROVIDER_FAILED')
    return result.stdout.strip()


def labels():
    return {'grid.audit.disposable':'1', 'grid.audit.repository':os.environ['GITHUB_REPOSITORY'],
            'grid.audit.run_id':os.environ['GITHUB_RUN_ID'],
            'grid.audit.run_attempt':os.environ['GITHUB_RUN_ATTEMPT']}


def local_daemon():
    hosted()
    context = json.loads(docker('context','inspect','default'))
    if len(context)!=1 or context[0]['Endpoints']['docker']['Host'] != 'unix:///var/run/docker.sock':
        raise RuntimeError('PG18_LOCAL_DOCKER_REQUIRED')


def attest():
    """Must succeed before opening ANY host PostgreSQL connection."""
    hosted()
    cid = os.environ.get('GRID_PG18_CONTAINER','')
    if not re.fullmatch(r'[0-9a-f]{64}',cid):
        raise RuntimeError('PG18_CONTAINER_ID_REQUIRED')
    local_daemon()
    rows = json.loads(docker('inspect',cid))
    if len(rows) != 1:
        raise RuntimeError('PG18_AMBIGUOUS_CONTAINER')
    c = rows[0]
    env = c['Config']['Env']
    ports = c['NetworkSettings']['Ports']['5432/tcp']
    port = os.environ.get('GRID_PG18_PORT','')
    if (c['Id'] != cid or c['State']['Running'] is not True
            or c['Config']['Image'] != IMAGE or c['Image'] != os.environ.get('GRID_PG18_IMAGE_ID')
            or any(c['Config'].get('Labels',{}).get(k)!=v for k,v in labels().items())
            or [x for x in env if x.startswith('PGDATA=')] != ['PGDATA='+PGDATA]
            or not {'POSTGRES_USER=grid','POSTGRES_DB=grid'} <= set(env)
            or not re.fullmatch(r'[0-9]{4,5}',port) or int(port) in (5432,55432,55433)
            or ports != [{'HostIp':'127.0.0.1','HostPort':port}]
            or c['HostConfig'].get('Binds')
            or c['HostConfig'].get('Privileged') is not False
            or c['HostConfig'].get('Tmpfs',{}).get(ROOT) != 'rw'
            or any(m.get('Type') != 'tmpfs' or m.get('Destination') != ROOT for m in c.get('Mounts',[]))):
        raise RuntimeError('PG18_DISPOSABLE_CONTAINER_PROOF_REJECTED')
    mountinfo = docker('exec',cid,'cat','/proc/self/mountinfo')
    if not any(len(x.split(' - '))==2 and x.split()[4]==ROOT
               and x.split(' - ')[1].split()[0]=='tmpfs' and 'rw' in x.split()[5].split(',')
               for x in mountinfo.splitlines()):
        raise RuntimeError('PG18_KERNEL_TMPFS_PROOF_REQUIRED')
    def sql(query):
        return docker('exec',cid,'psql','-X','-U','grid','-d','grid','-Atc',query)
    if sql('SHOW data_directory') != PGDATA or sql('SHOW server_version_num') != '180004':
        raise RuntimeError('PG18_EFFECTIVE_CLUSTER_MISMATCH')
    identity = sql('SELECT system_identifier::text FROM pg_catalog.pg_control_system()')
    if not re.fullmatch(r'[0-9]{1,20}',identity):
        raise RuntimeError('PG18_CLUSTER_IDENTITY_REQUIRED')
    return identity


def start():
    hosted()
    local_daemon()  # before secrets files, image pull or container creation
    secret = secrets.token_hex(32)
    print('::add-mask::'+secret, flush=True)
    secretfile = Path(os.environ['RUNNER_TEMP']) / 'grid-pg18-ci.env'
    secretfile.write_text('POSTGRES_PASSWORD='+secret+'\nPOSTGRES_USER=grid\nPOSTGRES_DB=grid\nPGDATA='+PGDATA+'\n')
    secretfile.chmod(0o600)
    docker('pull',IMAGE)
    args = ['run','--detach','--rm','--env-file',str(secretfile),'--tmpfs',ROOT+':rw',
            '-p','127.0.0.1::5432']
    for k,v in labels().items():
        args += ['--label',k+'='+v]
    cid = docker(*args,IMAGE)
    # The container is the only fixture this provider ever creates/removes.
    if not re.fullmatch(r'[0-9a-f]{64}',cid):
        raise RuntimeError('PG18_BAD_CREATED_CONTAINER_ID')
    c = json.loads(docker('inspect',cid))[0]
    values = {'GRID_PG18_CONTAINER':cid, 'GRID_PG18_IMAGE_ID':c['Image'],
              'GRID_PG18_PORT':c['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort'],
              'GRID_PG18_PASSWORD':secret}
    os.environ.update(values)
    with open(os.environ['GITHUB_ENV'],'a',encoding='utf-8') as f:
        for k,v in values.items():
            f.write(k+'='+v+'\n')
    for _ in range(45):
        try:
            identity = attest()
            Path('pg18-provider.json').write_text(json.dumps({
                'container':cid, 'image':IMAGE, 'image_id':c['Image'],
                'system_identifier':identity, 'run_id':os.environ['GITHUB_RUN_ID'],
                'exact_sha':os.environ['EXACT_HEAD_SHA'], 'disposable':True},indent=2))
            return
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError('PG18_ATTESTATION_FAILED_NO_HOST_SQL_ALLOWED')


def stop():
    hosted()
    local_daemon()  # never mutate an unproven default/remote Docker endpoint
    cid=os.environ.get('GRID_PG18_CONTAINER','')
    if not re.fullmatch(r'[0-9a-f]{64}',cid):
        raise RuntimeError('PG18_NO_OWNED_CONTAINER_RECEIPT')
    rows=json.loads(docker('inspect',cid))
    if len(rows)!=1 or any(rows[0]['Config'].get('Labels',{}).get(k)!=v for k,v in labels().items()):
        raise RuntimeError('PG18_CLEANUP_OWNERSHIP_UNPROVEN')
    docker('stop','--time','5',cid)
    secretfile=Path(os.environ['RUNNER_TEMP'])/'grid-pg18-ci.env'
    secretfile.unlink(missing_ok=True)


if __name__ == '__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in ('start','stop'):
        raise SystemExit('CI provider requires start or stop')
    try:
        {'start':start,'stop':stop}[sys.argv[1]]()
    except Exception:
        raise SystemExit('PG18_CI_PROVIDER_BLOCKED; no provider output or secrets logged') from None
