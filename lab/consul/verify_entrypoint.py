"""Exercise the actual optional coordinator startup on cloud-only disposable state."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit, urlunsplit
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import asyncpg
import httpx
from verify import checked


async def verify(manifest_path, output):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest['scope'] != 'CLOUD_DISPOSABLE_ONLY':raise ValueError('cloud manifest required')
    for voter in manifest['voters']:checked(manifest, voter)
    dsn = os.environ['MISSION3_TEST_DATABASE_URL']
    p = urlsplit(dsn)
    if p.hostname not in ('127.0.0.1', 'localhost') or p.path != '/grid_test' or p.query:
        raise ValueError('only explicit cloud-local grid_test fixture allowed')
    schema = 'entrypoint_' + uuid.uuid4().hex
    admin = await asyncpg.connect(dsn)
    # The current application schema audit explicitly targets public. A fresh
    # owned database preserves that contract without touching shared test tables.
    await admin.execute(f'CREATE DATABASE "{schema}"')
    isolated_dsn = urlunsplit((p.scheme, p.netloc, '/' + schema, '', ''))
    root = Path(output).parent / 'entrypoint-runtime'
    root.mkdir(parents=True, exist_ok=True)
    os.environ.update(POSTGRES_DSN=isolated_dsn,
        GRID_COORDINATION_MODE='consul', GRID_COORDINATION_ISOLATED_LAB='true',
        GRID_HA_REQUIRED='false', GRID_CONTROL_NODE_ID=schema,
        GRID_LEADER_LEASE_SECONDS='3', GRID_LEADER_RENEW_SECONDS='.2',
        GRID_LEADER_CLEANUP_TIMEOUT_SECONDS='3',
        CONSUL_ENDPOINTS=json.dumps([v['endpoint'] for v in manifest['voters']]),
        CONSUL_NAMESPACE='lab-grid/' + schema, GRID_SHARED_TOKEN='cloud-fixture-token',
        ProgramData=str(root), ProgramFiles=str(root / 'program-files'),
        ML_ARTIFACT_ROOT=str(root / 'artifacts'), ARCHIVE_ROOT=str(root / 'archive'),
        STRATEGY_CACHE_DIR=str(root / 'strategies'), LOG_LEVEL='WARNING')
    # These are manifest-verified local container IPs, not Internet proxy bypass.
    for name in ('NO_PROXY', 'no_proxy'):
        os.environ[name] = os.environ.get(name, '') + ',' + ','.join(v['ip'] for v in manifest['voters'])
    from grid import coordinator
    errors = []
    class ErrorCapture(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append({'logger': record.name, 'event': getattr(record, 'event', record.getMessage())})
    capture = ErrorCapture()
    logging.getLogger().addHandler(capture)
    started = False
    try:
        await coordinator.startup()
        started = True
        deadline = time.monotonic() + 30
        while not coordinator.control_leader.ready:
            if coordinator.control_leader.requires_fencing or time.monotonic() >= deadline:
                raise RuntimeError('coordinator did not initialize under current DCS/PG leadership')
            await asyncio.sleep(.05)
        await asyncio.sleep(.2)
        assert not errors, errors
        leader = coordinator.control_leader
        pg_epoch = leader.epoch
        dcs_token = leader.coordination_lease.token
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=coordinator.app), base_url='http://owned-cloud-app') as http:
            ready = await http.get('/ready')
            assert ready.status_code == 200 and ready.json()['physical_ha_qualified'] is False
            plugins = await http.get('/strategy/plugins', headers={'X-Grid-Token': 'cloud-fixture-token'})
            assert plugins.status_code == 200
            await coordinator.coordination_authority.release(leader.coordination_lease)
            blocked = await http.get('/strategy/plugins', headers={'X-Grid-Token': 'cloud-fixture-token'})
            assert blocked.status_code == 503 and blocked.json()['reason'] == 'COORDINATION_NOT_READY'
        leader.stop()
        await asyncio.wait_for(coordinator.control_task, 5)
        assert not leader.ready and not leader.is_leader and not coordinator.background_tasks
        result = {'schema': 'grid.consul.coordinator-entrypoint.v1', 'result': 'PASS',
                  'pg_epoch': pg_epoch, 'dcs_token': dcs_token,
                  'actual_singleton_services_started': True, 'startup_errors': errors, 'http_ready_while_owned': ready.status_code,
                  'http_after_session_loss': blocked.status_code, 'service_cleanup_confirmed': True,
                  'scope': 'ISOLATED_CLOUD_ONLY', 'database_isolation': 'OWNED_DATABASE_PUBLIC_SCHEMA', 'production_external_watchdog': 'NOT_QUALIFIED',
                  'physical_windows': 'NOT_RUN'}
        Path(output).write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    finally:
        if started:await coordinator.shutdown()
        logging.getLogger().removeHandler(capture)
        await admin.execute(f'DROP DATABASE IF EXISTS "{schema}"')
        await admin.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-isolated-cloud-lab', action='store_true', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    asyncio.run(verify(args.manifest, args.output))
