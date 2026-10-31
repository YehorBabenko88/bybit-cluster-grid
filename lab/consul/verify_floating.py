"""Couple real Consul sessions to existing PG fencing in cloud test schemas only."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import asyncpg
import httpx
from grid.coordination import ConsulConfig, ConsulSessionAuthority, CoordinationLost, floating_leader_guard
from grid.floating_leader import FloatingLeader
from verify import checked


async def verify(manifest_path, output):
    m = json.loads(Path(manifest_path).read_text())
    if m['scope'] != 'CLOUD_DISPOSABLE_ONLY':raise ValueError('cloud lab manifest required')
    for voter in m['voters']:checked(m, voter)
    dsn = os.environ['MISSION3_TEST_DATABASE_URL']
    p = urlsplit(dsn)
    if p.hostname not in ('127.0.0.1', 'localhost') or p.path != '/grid_test':
        raise ValueError('only explicit cloud-local grid_test fixture is allowed')
    schema = 'dcs_pg_' + uuid.uuid4().hex
    admin = await asyncpg.connect(dsn)
    pool = None
    async with httpx.AsyncClient(trust_env=False) as client:
        config = ConsulConfig(endpoints=tuple(v['endpoint'] for v in m['voters']),
                              namespace='lab-grid/' + schema, isolated_lab=True)
        a = ConsulSessionAuthority(config, client=client)
        b = ConsulSessionAuthority(config, client=client)
        leaders = []
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            await admin.execute(f'''CREATE TABLE "{schema}".service_leases(
                service_key text PRIMARY KEY, owner text NOT NULL, lease_until timestamptz,
                heartbeat_at timestamptz, metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb)''')
            async def setup(conn):await conn.execute(f'SET search_path TO "{schema}"')
            pool = await asyncpg.create_pool(dsn, min_size=2, max_size=4, setup=setup)
            leaders = [FloatingLeader(pool, 'node-a', 3, 1, coordination=a),
                       FloatingLeader(pool, 'node-b', 3, 1, coordination=b)]
            outcomes = await asyncio.gather(*(x.campaign() for x in leaders))
            assert sorted(outcomes) == [False, True]
            winner = leaders[outcomes.index(True)]
            contender = leaders[outcomes.index(False)]
            first_epoch = winner.epoch
            old_dcs_lease = winner.coordination_lease
            first_token = old_dcs_lease.token
            guard = floating_leader_guard(winner)
            assert await guard() == {'owner': winner.node_id, 'epoch': first_epoch}
            assert await winner.renew()
            await winner.coordination.release(winner.coordination_lease)
            try:await guard()
            except CoordinationLost:pass
            else:raise AssertionError('DCS loss must fence live PG row')
            assert not await winner.renew() and winner.epoch is None
            # A DCS lock alone cannot seize an unexpired resource-side PG lease.
            assert await contender.campaign() is False
            await asyncio.sleep(3.1)
            assert await contender.campaign() is True
            assert contender.epoch > first_epoch and contender.coordination_lease.token > first_token
            assert await winner.release(first_epoch) == 'UPDATE 0'
            assert await contender.renew()
            await contender.coordination.write_control(contender.coordination_lease, 'placements',
                                                       {'job': 'reassigned', 'owner': contender.node_id})
            stored = await contender.coordination.read_control('placements')
            assert stored['owner'] == contender.node_id
            import base64
            stale = [
                {'KV': {'Verb': 'check-session', 'Key': config.namespace + '/leader', 'Session': old_dcs_lease.session_id}},
                {'KV': {'Verb': 'check-index', 'Key': config.namespace + '/leader', 'Index': first_token}},
                {'KV': {'Verb': 'set', 'Key': config.namespace + '/state/placements',
                        'Value': base64.b64encode(b'{"owner":"stale-writer"}').decode()}},
            ]
            denied = await client.put(config.endpoints[0] + '/v1/txn', json=stale, timeout=2)
            assert denied.status_code == 409 and denied.json()['Errors']
            assert (await contender.coordination.read_control('placements'))['owner'] == contender.node_id
            result = {'schema': 'grid.consul.pg-coupling.v1', 'result': 'PASS',
                      'first_pg_epoch': first_epoch, 'first_dcs_token': first_token,
                      'successor_pg_epoch': contender.epoch, 'successor_dcs_token': contender.coordination_lease.token,
                      'durable_reassignment': stored, 'physical_windows': 'NOT_RUN',
                      'cross_resource_atomicity': 'NOT_CLAIMED', 'server_stale_transaction_status': denied.status_code}
            Path(output).write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
        finally:
            for leader in leaders:await leader.shutdown()
            if pool is not None:await pool.close()
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-isolated-cloud-lab', action='store_true', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    asyncio.run(verify(args.manifest, args.output))
