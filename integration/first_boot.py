"""Plan-only by default. Real first boot exclusively in disposable hosted PG18 CI."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from .first_boot_policy import ROOT,require_ci,child_environment,loopback_endpoint


async def until(function,timeout=90):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=await function()
        if value:return value
        await asyncio.sleep(.3)
    raise RuntimeError('FIRST_BOOT_CONDITION_TIMEOUT')


def registration_is_fresh(nodes,previous,restarted):
    if set(nodes)!=set(previous):return False
    for name,current in nodes.items():
        if current.get('integrity_ok') is not True:return False
        if current.get('last_seen') is None or current['last_seen']<=previous[name].get('last_seen',current['last_seen']):return False
        if name in restarted and (not current.get('collector_session') or current['collector_session']==previous[name].get('collector_session')):return False
    return True


async def execute():
    require_ci()
    from tools.check_ddl_free_ci import verify_checkout
    from tools.ci_pg18 import attest,docker,PGDATA
    from tests._pg18_database import database,grant_runtime
    from grid.schema_preparation import prepare_schema
    from grid.schema_contract import verify_runtime_schema,catalog_digest
    from .first_boot_evidence import Evidence
    from .first_boot_process import OwnedChild,stop_all
    from .synthetic_feed import SyntheticFeed,SYMBOLS
    import aiohttp
    import asyncpg
    head=os.environ['EXACT_HEAD_SHA'];verify_checkout(ROOT,head)
    if (ROOT/'.env').exists():raise RuntimeError('FIRST_BOOT_DOTENV_FORBIDDEN')
    attest()  # before any PostgreSQL connection or fixture creation
    evidence=Evidence(ROOT/'first-boot-evidence',head);children=[];redactions={os.environ['GRID_PG18_PASSWORD']};error=None
    root=Path(tempfile.mkdtemp(prefix='grid-first-boot-',dir=os.environ['RUNNER_TEMP']));root_identity=(root.stat().st_dev,root.stat().st_ino)
    (root/'owned.json').write_text(json.dumps(dict(head=head,run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])))
    feed=SyntheticFeed();co=None;worker_children={};credentials={}
    def mask(secret):
        redactions.add(secret);print('::add-mask::'+secret,flush=True)
    token=secrets.token_hex(32);mask(token)
    def node_dir(name):
        p=root/name;p.mkdir()
        for n in ('data','programs','temp'): (p/n).mkdir()
        return p
    def port():
        with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
    api='http://127.0.0.1:'+str(port());loopback_endpoint(api)
    control_root=node_dir('control');node_roots={n:node_dir(n) for n in ('synthetic-a','synthetic-b')}
    files={}
    for n in subprocess.check_output(['git','ls-files','grid','integration','run_worker.py','run_coordinator.py'],cwd=ROOT,text=True).splitlines():
        if n.endswith('.py'):files[n]=hashlib.sha256((ROOT/n).read_bytes()).hexdigest()
    manifest=root/'release-manifest.json';manifest.write_text(json.dumps(dict(version=head,files=files)))
    @asynccontextmanager
    async def runtime_lifetime():
        try:yield
        finally:
            # Reverse context exit happens BEFORE DROP DATABASE in the PG fixture.
            await stop_all(children)
    try:
        await feed.start()
        async with database(False) as (p,roles,options,dbname,admin),runtime_lifetime():
            if await prepare_schema(p['owner'])!='PREPARED':raise RuntimeError('FIRST_BOOT_PREPARATION')
            evidence.case('schema-preparation')
            versions=await p['owner'].fetch('SELECT version FROM schema_migrations ORDER BY version')
            if [r['version'] for r in versions]!=list(range(1,49)):raise RuntimeError('FIRST_BOOT_MIGRATIONS')
            evidence.case('registry-1-48')
            if await prepare_schema(p['owner'])!='ALREADY_PREPARED':raise RuntimeError('FIRST_BOOT_IDEMPOTENCY')
            evidence.case('preparation-idempotent');await grant_runtime(p['owner'],roles);await verify_runtime_schema(p['app'])
            try:await p['app'].execute('CREATE TABLE public.forbidden_first_boot(x integer)')
            except asyncpg.InsufficientPrivilegeError:pass
            else:raise RuntimeError('APP_HAS_DDL')
            evidence.case('runtime-minimum-rights')
            await p['ro'].fetchval('SELECT count(*) FROM candles_1m')
            try:await p['ro'].execute('DELETE FROM candles_1m')
            except asyncpg.InsufficientPrivilegeError:pass
            else:raise RuntimeError('RO_HAS_WRITES')
            evidence.case('read-only-role')
            async with p['owner'].acquire() as c:before=await catalog_digest(c)
            async def start_control():
                env=child_environment(os.environ,control_root,'coordinator',api,feed.url,head)
                env.update(GRID_SHARED_TOKEN=token,POSTGRES_DSN=f'postgresql://{roles["app"]}@127.0.0.1:{options["port"]}/{dbname}',PGPASSWORD=os.environ['GRID_PG18_PASSWORD'])
                child=OwnedChild(env,control_root,'coordinator',redactions);children.append(child);await child.start();return child
            co=await start_control()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
                async def health():
                    try:
                        async with http.get(api+'/health') as r:
                            if r.status!=200:return False
                            value=await r.json();return value if value.get('pid')==co.process.pid and value.get('control_leader') is True and value.get('control_epoch',0)>0 else False
                    except (aiohttp.ClientError,TimeoutError):return False
                await until(health);evidence.case('foreground-coordinator')
                # Private control is sequenced; real enrollment HTTP requests can race.
                enrollments=[]
                for n in node_roots:enrollments.append((n,await co.command('enrollment-token')));mask(enrollments[-1][1])
                async def enroll_given(pair):
                    n,one_time=pair
                    async with http.post(api+'/enroll',json=dict(enrollment_token=one_time,node_id=n)) as r:
                        if r.status!=200:raise RuntimeError('ENROLLMENT_FAILED')
                        value=await r.json();credentials[n]=value['credential'];mask(value['credential'])
                await asyncio.gather(*(enroll_given(x) for x in enrollments));evidence.case('concurrent-enrollment')
                async with http.post(api+'/enroll',json=dict(node_id='replayed',enrollment_token=enrollments[0][1])) as r:
                    if r.status!=401:raise RuntimeError('ENROLLMENT_REPLAY_ACCEPTED')
                evidence.case('enrollment-replay-rejected')
                async def start_worker(n):
                    env=child_environment(os.environ,node_roots[n],'worker',api,feed.url,head)
                    env.update(NODE_ID=n,NODE_CREDENTIAL=credentials[n],GRID_RELEASE_MANIFEST=str(manifest),GRID_INSTALL_ROOT=str(ROOT))
                    child=OwnedChild(env,node_roots[n],n,redactions);children.append(child);await child.start();worker_children[n]=child
                for n in node_roots:await start_worker(n)
                async def all_registered():
                    value=await co.command('status');return value if set(value['nodes'])==set(node_roots) and all(x['integrity_ok'] is True for x in value['nodes'].values()) else False
                await until(all_registered);evidence.case('two-real-workers')
                if feed.connections or feed.frames:raise RuntimeError('INFRA_ONLY_OPENED_MARKET')
                evidence.case('infra-no-market')
                async with http.post(api+'/ingest/minute',json={},headers={'X-Node-ID':'synthetic-a','X-Node-Credential':'wrong'}) as r:
                    if r.status!=403:raise RuntimeError('BAD_AUTH_ACCEPTED')
                evidence.case('ingest-auth-rejected')
                headers={'X-Node-ID':'synthetic-a','X-Node-Credential':credentials['synthetic-a']}
                async with http.post(api+'/ingest/minute',json={},headers=headers) as r:
                    if r.status!=423:raise RuntimeError('INFRA_GATE_OPEN')
                evidence.case('infra-ingest-locked')
                await co.command('fleet-stop')
                async def stopped():
                    h=await health();return h and h['runtime_state']=='STOPPED'
                await until(stopped);evidence.case('fleet-stop-ack')
                for n in node_roots:await co.command('pilot-validate',n)
                evidence.case('pilot-validation');await co.command('fleet-resume')
                async def active():
                    h=await health();return h and h['runtime_state']=='ACTIVE'
                await until(active);evidence.case('fleet-resume-ack')
                async def assigned():
                    state=await co.command('status');flat=[s for symbols in state['assignments'].values() for s in symbols]
                    return state if sorted(flat)==sorted(SYMBOLS) and len(flat)==len(set(flat)) else False
                await until(assigned);evidence.case('exclusive-assignments')
                async def fresh_collection():
                    await feed.advance()
                    marker=feed.minute_start
                    async def fresh():
                        count=await p['app'].fetchval("SELECT count(DISTINCT symbol) FROM candles_1m WHERE ts=to_timestamp($1/1000.0) AND trade_count=2 AND buy_volume=2 AND sell_volume=1",marker)
                        receipts=await p['app'].fetchval("SELECT count(*) FROM collection_ingest_receipts WHERE disposition='LIVE' AND kind='minute' AND (payload::jsonb->>'start_ms')::bigint=$1",marker)
                        return count==2 and receipts>=2
                    await until(fresh)
                async def persisted():
                    rows=await p['app'].fetch('SELECT symbol,trade_count,buy_volume,sell_volume FROM candles_1m ORDER BY symbol')
                    if len(rows)<2:return False
                    if any(r['trade_count']!=2 or float(r['buy_volume'])!=2 or float(r['sell_volume'])!=1 for r in rows):raise RuntimeError('SYNTHETIC_STATISTICS_CORRUPTED')
                    return rows
                await until(persisted);evidence.case('synthetic-pipeline-postgres')
                feed.pause=True;await asyncio.sleep(2)
                receipt=await p['app'].fetchrow("SELECT node_id,payload FROM collection_ingest_receipts WHERE kind='minute' AND disposition='LIVE' LIMIT 1")
                if not receipt:raise RuntimeError('NO_REAL_MINUTE_RECEIPT')
                payload=json.loads(receipt['payload']) if isinstance(receipt['payload'],str) else receipt['payload']
                h={'X-Node-ID':receipt['node_id'],'X-Node-Credential':credentials[receipt['node_id']]}
                async with http.post(api+'/ingest/minute',json=payload,headers=h) as r:
                    if r.status!=200:raise RuntimeError('DUPLICATE_REJECTED')
                await persisted();evidence.case('duplicate-ingest-idempotent')
                changed=dict(payload,delta=float(payload.get('delta',0))+1)
                async with http.post(api+'/ingest/minute',json=changed,headers=h) as r:
                    if r.status!=400:raise RuntimeError('CHANGED_DELIVERY_ACCEPTED')
                evidence.case('changed-delivery-rejected')
                previous=(await co.command('status'))['nodes']
                first=next(iter(node_roots));await worker_children[first].stop(crash=True);await start_worker(first)
                async def fresh_workers():
                    state=await co.command('status')
                    return state if registration_is_fresh(state['nodes'],previous,{first}) else False
                await until(fresh_workers)
                await fresh_collection()
                evidence.case('worker-crash-restart')
                await co.stop(crash=True);co=await start_control();await until(health,120);await until(all_registered);await fresh_collection()
                evidence.case('coordinator-crash-recovery')
                # This restarts PostgreSQL INSIDE the attested container, preserving tmpfs mount/cluster ID.
                identity=attest();docker('exec','--user','postgres',os.environ['GRID_PG18_CONTAINER'],'pg_ctl','-D',PGDATA,'restart','-m','fast','-w','-t','20')
                if attest()!=identity:raise RuntimeError('POSTGRES_RESTART_CHANGED_CLUSTER')
                await until(health,120);await until(all_registered);await fresh_collection();await persisted();evidence.case('postgres-restart-recovery')
                for child in worker_children.values():await child.stop()
                await co.stop();co=await start_control();await until(health,120)
                for n in node_roots:await start_worker(n)
                await until(all_registered);await fresh_collection();await persisted();evidence.case('persisted-state-restart')
                for child in worker_children.values():await child.stop()
                await co.stop();evidence.case('controlled-shutdown')
                async with p['owner'].acquire() as c:
                    if await catalog_digest(c)!=before:raise RuntimeError('RUNTIME_SCHEMA_CHANGED')
                evidence.case('catalog-unchanged')
    except Exception as exc:error=type(exc).__name__
    finally:
        for child in reversed(children):
            try:
                if child.process and child.process.returncode is None:await child.stop()
            except Exception:error=error or 'ProcessCleanupFailed'
            code=child.process.returncode if child.process else None
            evidence.processes.append(dict(name=child.label,pid=child.process.pid if child.process else None,exit_code=code))
            (evidence.path/(child.label+'-'+str(len(evidence.processes))+'.log')).write_text('\n'.join(child.logs),encoding='utf-8')
        await feed.close()
        try:
            if any(c.process and c.process.returncode is None for c in children):raise RuntimeError('OWNED_CHILD_STILL_RUNNING')
            if (root.stat().st_dev,root.stat().st_ino)!=root_identity or root.is_symlink() or not (root/'owned.json').is_file():raise RuntimeError('OWNED_ROOT_CHANGED')
            for path in root.rglob('*'):
                if path.is_symlink() or path.is_file() and path.stat().st_nlink!=1:raise RuntimeError('UNSAFE_FIXTURE_LINK_RETAINED')
            if not shutil.rmtree.avoids_symlink_attacks:raise RuntimeError('FD_SAFE_CLEANUP_UNAVAILABLE')
            shutil.rmtree(root);evidence.case('owned-cleanup')
        except Exception:error=error or 'OwnedCleanupBlocked'
    success=evidence.finish(error)
    print(json.dumps(dict(core_status='ISOLATED_E2E_PASS' if success else 'BLOCKED',physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')))
    return 0 if success else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute-ci',action='store_true');args=parser.parse_args()
    if not args.execute_ci:
        print(json.dumps(dict(status='PLAN_ONLY',physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')));return 0
    try:return asyncio.run(execute())
    except Exception as exc:
        print(json.dumps(dict(status='BLOCKED',error_class=type(exc).__name__,physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')));return 1


if __name__=='__main__':raise SystemExit(main())
