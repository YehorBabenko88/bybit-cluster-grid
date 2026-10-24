"""Foreground real Grid process adapter. Disposable hosted Linux CI only."""
import asyncio
import datetime
import json
import os
from pathlib import Path
import signal
import sys
from .first_boot_policy import require_ci,install_child_guard,loopback_endpoint,ROOT

PREFIX='FIRST_BOOT_PRIVATE_CONTROL:'


def emit(sequence,ok,value):
    # Private pipe only. Enrollment secrets MUST NOT be copied to artifacts/logs.
    print(PREFIX+json.dumps(dict(id=sequence,nonce=os.environ['GRID_FIXTURE_NONCE'],ok=ok,value=value)),flush=True)


async def coordinator():
    import uvicorn
    from grid import coordinator as co
    from grid.control_runtime import epoch_context
    from grid.enrollment import create_enrollment_token
    from grid.fleet_control import fleet_stop,fleet_resume
    from grid.server_pilot import begin_server_pilot_validation
    host,port=loopback_endpoint(os.environ['COORDINATOR_URL'])
    server=uvicorn.Server(uvicorn.Config(co.app,host=host,port=port,log_level='warning',access_log=False,timeout_graceful_shutdown=20))
    task=asyncio.create_task(server.serve())
    reader=asyncio.StreamReader(limit=65536);protocol=asyncio.StreamReaderProtocol(reader)
    transport,_=await asyncio.get_running_loop().connect_read_pipe(lambda:protocol,sys.stdin.buffer)
    async def commands():
        while True:
            raw=await reader.readline()
            if not raw:server.should_exit=True;return
            command=None
            try:
                command=json.loads(raw)
                if set(command)!={'id','nonce','action','node'} or command['nonce']!=os.environ['GRID_FIXTURE_NONCE'] or type(command['id']) is not int:
                    raise ValueError('private control binding')
                action=command['action'];node=command['node']
                if action=='shutdown':server.should_exit=True;emit(command['id'],True,{'state':'SHUTTING_DOWN'});return
                runtime=co.control_runtime
                if runtime is None or not runtime.ready or runtime.token is None:raise RuntimeError('leader not ready')
                with epoch_context(runtime.token):
                    async with co.db.pool.effect_guard():
                        if action=='enrollment-token':
                            value=await create_enrollment_token(co.db.pool,'isolated-first-boot',datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=15),'PILOT')
                        elif action=='fleet-stop':value=await fleet_stop(co.db.pool,co.nodes,'isolated-ci-operator')
                        elif action=='fleet-resume':value=await fleet_resume(co.db.pool,co.nodes,'isolated-ci-operator')
                        elif action=='pilot-validate':
                            state=await begin_server_pilot_validation(co.db.pool,node,co.nodes,co.settings.heartbeat_seconds)
                            value={k:state.get(k) for k in ('mode','phase')}
                        elif action=='status':
                            keys=('last_seen','operator_stopped','wanted_symbols','active_trade_streams','integrity_ok','collector_session','runtime_state','db_queue_depth','micro_queue_depth','db_replay_active','micro_replay_active')
                            value=dict(nodes={k:{f:v.get(f) for f in keys} for k,v in co.nodes.items()},assignments=co.assignments,instruments=list(co.instruments))
                        else:raise ValueError('private action refused')
                emit(command['id'],True,value)  # after fence transaction commit
            except Exception as exc:
                emit(command.get('id',-1) if isinstance(command,dict) else -1,False,{'error_class':type(exc).__name__})
    command_task=asyncio.create_task(commands())
    try:
        done,_=await asyncio.wait((task,command_task),return_when=asyncio.FIRST_COMPLETED)
        if command_task in done:
            await command_task;server.should_exit=True
        await asyncio.wait_for(task,30)
        if not server.started:raise RuntimeError('coordinator did not start')
    finally:
        command_task.cancel();await asyncio.gather(command_task,return_exceptions=True);transport.close()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)


async def worker():
    from grid.worker import Worker
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
    task=asyncio.create_task(Worker().run());wait=asyncio.create_task(stop.wait())
    try:
        done,_=await asyncio.wait((task,wait),return_when=asyncio.FIRST_COMPLETED)
        if task in done:await task
        else:task.cancel();await asyncio.gather(task,return_exceptions=False)
    except asyncio.CancelledError:
        if not stop.is_set():raise
    finally:
        wait.cancel();await asyncio.gather(wait,return_exceptions=True)


async def run():
    require_ci()  # no SQL, application import, native/physical collection before this gate
    if (ROOT/'.env').exists():raise RuntimeError('dotenv forbidden')
    root=Path(os.environ['GRID_FIXTURE_ROOT']).resolve(strict=True)
    marker=json.loads((root/'owned.json').read_text())
    if marker!={k:os.environ[k] for k in ('EXACT_HEAD_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GRID_FIXTURE_NONCE')}:
        raise RuntimeError('fixture marker mismatch')
    loopback_endpoint(os.environ['COORDINATOR_URL']);loopback_endpoint(os.environ['BYBIT_REST_URL']);loopback_endpoint(os.environ['BYBIT_WS_URL'])
    if os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TAILSCALE_OAUTH_CLIENT_ID') or os.environ.get('TAILSCALE_OAUTH_CLIENT_SECRET'):
        raise RuntimeError('external credentials forbidden')
    role=os.environ['ROLE']
    if role not in ('coordinator','worker') or role=='worker' and (os.environ.get('POSTGRES_DSN') or os.environ.get('PGPASSWORD')):
        raise RuntimeError('worker database credentials forbidden')
    if role=='coordinator' and not os.environ.get('GRID_SHARED_TOKEN'):raise RuntimeError('missing synthetic administrative credential')
    install_child_guard(root)
    emit(0,True,dict(pid=os.getpid(),role=role,head=os.environ['EXACT_HEAD_SHA']))
    await (coordinator() if role=='coordinator' else worker())


if __name__=='__main__':
    try:asyncio.run(run())
    except Exception as exc:raise SystemExit('FIRST_BOOT_CHILD_FAILED:'+type(exc).__name__) from None
