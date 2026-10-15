"""Opt-in disposable CI database; never uses installed Grid databases/ports."""
from contextlib import asynccontextmanager
import os
import json
import re
import subprocess
import uuid
from urllib.parse import urlsplit
import asyncpg
import pytest


def disposable_source_dsn():
    if os.environ.get('GRID_DISPOSABLE_POSTGRES_TESTS') != '1':
        pytest.skip('requires explicit disposable PostgreSQL CI opt-in')
    dsn=os.environ.get('POSTGRES_DSN','')
    u=urlsplit(dsn)
    if (u.scheme not in {'postgres','postgresql'} or u.hostname not in {'localhost','127.0.0.1','::1'}
            or u.path!='/grid' or u.port in {55432,55433} or u.query or u.fragment):
        raise RuntimeError('disposable tests require loopback CI database grid; installed Grid ports prohibited')
    return dsn


def attest_ci_container(dsn):
    # Local-only proof before opening a host PostgreSQL connection. Environment
    # opt-in alone cannot distinguish an installed cluster from a CI service.
    env=os.environ
    container=env.get('GRID_TEST_POSTGRES_CONTAINER_ID','')
    if (env.get('GITHUB_ACTIONS')!='true' or env.get('RUNNER_ENVIRONMENT')!='github-hosted'
            or env.get('RUNNER_OS')!='Linux'
            or env.get('GITHUB_REPOSITORY')!='YehorBabenko88/bybit-cluster-grid'
            or env.get('GITHUB_JOB')!='python-preflight'
            or not re.fullmatch(r'[1-9][0-9]*',env.get('GITHUB_RUN_ID',''))
            or not re.fullmatch(r'[1-9][0-9]*',env.get('GITHUB_RUN_ATTEMPT',''))
            or not re.fullmatch(r'[0-9a-f]{64}',container)
            or env.get('DOCKER_HOST') or env.get('DOCKER_CONTEXT')
            or urlsplit(dsn).hostname!='127.0.0.1' or urlsplit(dsn).username!='grid'):
        raise RuntimeError('disposable CI service attestation required before connection')
    def docker(*args):
        result=subprocess.run(['docker','--context','default',*args],capture_output=True,
                              text=True,timeout=10,check=False)
        if result.returncode:raise ValueError('provider failed')
        return result.stdout
    stage='docker_context'
    try:
        context=json.loads(docker('context','inspect','default'))
        if context[0]['Endpoints']['docker']['Host']!='unix:///var/run/docker.sock':raise ValueError('nonlocal Docker')
        stage='container_inspect'
        rows=json.loads(docker('inspect',container))
        if len(rows)!=1:raise ValueError('ambiguous container')
        info=rows[0]
        stage='container_environment'
        settings=info['Config'];values=set(settings.get('Env',[]))
        pgdata='/var/lib/postgresql/data'
        if [v for v in settings.get('Env',[]) if v.startswith('PGDATA=')]!=['PGDATA='+pgdata]:
            raise ValueError('unreviewed data directory')
        if any(p.get('Destination','').startswith(pgdata+'/') for p in info.get('Mounts',[])):
            raise ValueError('nested data mount')
        labels=settings.get('Labels') or {}
        required={'grid.audit.disposable':'1','grid.audit.run_id':env['GITHUB_RUN_ID'],
                  'grid.audit.run_attempt':env['GITHUB_RUN_ATTEMPT'],
                  'grid.audit.repository':env['GITHUB_REPOSITORY']}
        stage='ephemeral_mount_and_labels'
        ephemeral=(info.get('HostConfig',{}).get('Tmpfs',{}).get('/var/lib/postgresql/data')=='rw'
                   and any(p.get('Type')=='tmpfs' and p.get('Destination')=='/var/lib/postgresql/data'
                           for p in info.get('Mounts',[])))
        if not ephemeral:
            raise ValueError('ephemeral mount proof rejected')
        stage='current_run_labels'
        if any(labels.get(k)!=v for k,v in required.items()):
            raise ValueError('current-run label proof rejected')
        stage='container_port_and_image'
        port=str(urlsplit(dsn).port or 5432)
        mappings=info['NetworkSettings']['Ports']['5432/tcp']
        if (info['Id']!=container or info['State']['Running'] is not True
                or settings['Image']!='postgres:16'
                or not {'POSTGRES_DB=grid','POSTGRES_USER=grid'}<=values
                or not mappings or any(p['HostPort']!=port or p['HostIp'] not in {'0.0.0.0','127.0.0.1','::'} for p in mappings)):
            raise ValueError('service mismatch')
        stage='effective_data_directory'
        directory=docker('exec',container,'psql','-h','/var/run/postgresql','-p','5432','-X','-U','grid','-d','grid','-A','-t','-c','SHOW data_directory').strip()
        if directory!=pgdata:raise ValueError('effective data directory mismatch')
        stage='container_cluster_identity'
        identity=docker('exec',container,'psql','-h','/var/run/postgresql','-p','5432','-X','-U','grid','-d','grid','-A','-t','-c',
                        'SELECT system_identifier::text FROM pg_catalog.pg_control_system()').strip()
        if not re.fullmatch(r'[0-9]{1,20}',identity):raise ValueError('invalid cluster identity')
        return identity
    except Exception:
        # Fixed diagnostic stage names only. Never expose provider output, DSNs or credentials.
        raise RuntimeError('disposable CI container attestation failed at stage: '+stage) from None


@asynccontextmanager
async def disposable_database():
    dsn=disposable_source_dsn()  # guard before any connection
    identity=attest_ci_container(dsn)
    name='grid_audit48_'+uuid.uuid4().hex
    admin=await asyncpg.connect(dsn,command_timeout=5,server_settings={
        'default_transaction_read_only':'on','statement_timeout':'5000','lock_timeout':'1000'})
    pool=None;created=False
    try:
        actual=await admin.fetchval('SELECT system_identifier::text FROM pg_catalog.pg_control_system()')
        if actual!=identity:raise RuntimeError('disposable PostgreSQL cluster identity mismatch')
        await admin.execute('SET default_transaction_read_only=off')
        await admin.execute('CREATE DATABASE "'+name+'" TEMPLATE template0')
        created=True
        pool=await asyncpg.create_pool(dsn,database=name,min_size=2,max_size=5,
                                      server_settings={'search_path':'public'})
        yield pool
    finally:
        if pool:await pool.close()
        if created:
            # Only the UUID database created in this context can be cleaned up.
            assert name.startswith('grid_audit48_') and name[13:].isalnum()
            await admin.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1 AND pid<>pg_backend_pid()',name)
            await admin.execute('DROP DATABASE "'+name+'"')
        await admin.close()
