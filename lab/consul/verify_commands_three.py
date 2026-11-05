"""Explicit Linux-hosted three-persistent-voter command qualification.

Uses the existing immutable Consul image pin. Never run on office machines.
Plaintext isolated fixture is NOT human-auth, mTLS, Windows or physical proof.
No missing prerequisites are converted into SKIP/PASS. Failed evidence retained.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import httpx
from grid.coordination import ConsulConfig, ConsulSessionAuthority
from grid.coordination_commands import CoordinationCommands, CurrentPrincipal
from provision import IMAGE, docker

SOURCE_COMMIT = '881572b49b5d4d67713fa7f8ff09ed0ff2befc0f'


class SyntheticLabProvider:
    async def require_current(self, context, action, aggregate_id):
        if context != 'SYNTHETIC_AUTH':
            raise ValueError('synthetic lab identity only')
        return CurrentPrincipal('lab-human', 1, 'HUMAN',
                                frozenset({'research.control', 'control.commands.read'}))


async def verify(output):
    if sys.platform != 'linux':
        raise RuntimeError('ISOLATED_HOSTED_LINUX_REQUIRED')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    label = 'mission4-consul-commands-' + uuid.uuid4().hex[:12]
    network = label + '-net'
    nodes = []
    evidence = dict(schema='grid.consul.commands.three.v1', image=IMAGE, label=label,
                    native_windows='NOT_RUN', physical='NOT_RUN', production_tls_acl='NOT_RUN',
                    snapshot_restore='NOT_RUN', backup_restore='NOT_RUN',
                    human_authentication='SYNTHETIC_AUTH', result='RUNNING', events=[])

    def record(name, **fields):
        evidence['events'].append(dict(scenario=name, **fields))
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2))

    def inspect(node):
        info = json.loads(docker('inspect', node['id']))[0]
        if (info['Id'] != node['id'] or info['Config']['Image'] != IMAGE
                or info['Config']['Labels'].get('grid.lab') != label
                or info['HostConfig']['RestartPolicy']['Name'] != 'no'
                or not any(m['Name'] == node['volume'] and m['Destination'] == '/consul/data'
                           for m in info['Mounts'])):
            raise RuntimeError('OWNED_CONTAINER_IDENTITY_MISMATCH')
        node['ip'] = info['NetworkSettings']['Networks'].get(network, {}).get('IPAddress')
        if node['ip']:
            node['last_ip'] = node['ip']
        return info

    def endpoint(node):
        inspect(node)
        if not node['ip']:
            raise RuntimeError('LAB_ENDPOINT_UNAVAILABLE')
        return 'http://' + node['ip'] + ':8500'

    async def wait_healthy(http, live):
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            try:
                for owned in nodes:
                    inspect(owned)
                expected = {n['name']: n for n in nodes}
                for node in live:
                    response = await http.get(endpoint(node) + '/v1/operator/raft/configuration')
                    response.raise_for_status()
                    servers = response.json()['Servers']
                    if (len(servers) != 3 or sum(s['Leader'] is True for s in servers) != 1
                            or {s['Node'] for s in servers} != set(expected)
                            or len({s['ID'] for s in servers}) != 3
                            or any(s['Voter'] is not True for s in servers)):
                        raise ValueError('three voters and one leader required')
                    for server in servers:
                        owned = expected[server['Node']]
                        if (str(uuid.UUID(server['ID'])) != server['ID']
                                or server['Address'] != owned['last_ip'] + ':8300'
                                or ('raft_id' in owned and owned['raft_id'] != server['ID'])):
                            raise ValueError('exact stable voter identity/address required')
                        owned['raft_id'] = server['ID']
                record('verified_voter_configuration', servers=servers)
                return
            except (httpx.HTTPError, ValueError, KeyError, RuntimeError):
                await asyncio.sleep(.3)
        raise RuntimeError('THREE_VOTER_QUORUM_TIMEOUT')

    try:
        image_info = json.loads(docker('image', 'inspect', IMAGE))[0]
        if IMAGE not in image_info.get('RepoDigests', []):
            raise RuntimeError('EXPECTED_IMAGE_DIGEST_REQUIRED')
        version_output = docker('run', '--rm', '--network=none', '--entrypoint=consul', IMAGE, 'version')
        if 'Consul v2.1.0' not in version_output or SOURCE_COMMIT[:8] not in version_output:
            raise RuntimeError('EXPECTED_CONSUL_VERSION_SOURCE_REQUIRED')
        record('immutable_image_version_source_checked', image_id=image_info['Id'],
               repo_digests=image_info['RepoDigests'], version_output=version_output,
               expected_source_commit=SOURCE_COMMIT,
               upstream_source='https://github.com/hashicorp/consul/releases/tag/v2.1.0',
               supply_chain_attestation='NOT_VERIFIED')
        docker('network', 'create', '--internal', '--label', 'grid.lab=' + label, network)
        net = json.loads(docker('network', 'inspect', network))[0]
        if not net['Internal'] or net['Labels'].get('grid.lab') != label:
            raise RuntimeError('OWNED_INTERNAL_NETWORK_REQUIRED')
        names = [label + '-' + suffix for suffix in ('ls5', 'pc4', 'pc3')]
        for name in names:
            volume = name + '-data'
            docker('volume', 'create', '--label', 'grid.lab=' + label, volume)
            args = ['run', '-d', '--name', name, '--hostname', name, '--network', network,
                '--label', 'grid.lab=' + label, '--restart=no', '--memory=256m', '--cpus=.5',
                '--mount', 'type=volume,source=' + volume + ',target=/consul/data',
                '-e', 'CONSUL_LOCAL_CONFIG=' + json.dumps({'leave_on_terminate': False,
                    'autopilot': {'cleanup_dead_servers': False}}), IMAGE, 'agent', '-server',
                '-bootstrap-expect=3', '-node=' + name, '-client=0.0.0.0', '-bind=0.0.0.0',
                '-data-dir=/consul/data', '-retry-interval=1s']
            args.extend('-retry-join=' + peer for peer in names if peer != name)
            nodes.append(dict(id=docker(*args), name=name, volume=volume))
        evidence['nodes'] = nodes
        record('persistent_voters_created')
        async with httpx.AsyncClient(trust_env=False, timeout=3) as http:
            await wait_healthy(http, nodes)
            generation = str(uuid.uuid4())
            namespace = 'lab-' + uuid.uuid4().hex
            # Owner provisioning is isolated here; runtime bridge cannot create generations.
            response = await http.put(endpoint(nodes[0]) + '/v1/kv/' + namespace + '/commands/generation',
                                      json={'generation': generation})
            response.raise_for_status()
            authority = ConsulSessionAuthority(ConsulConfig(endpoints=tuple(endpoint(n) for n in nodes),
                namespace=namespace, isolated_lab=True), client=http)
            bridge = CoordinationCommands(authority, generation, principal_provider=SyntheticLabProvider())
            lease = await authority.acquire('LS5')
            if lease is None:
                raise RuntimeError('NO_INITIAL_COMMAND_LEASE')
            intent = dict(schema='unified.command.v1', command_id=str(uuid.uuid4()), actor_id='lab-human', idempotency_key='first',
                generation=generation, aggregate_type='research', aggregate_id='main',
                expected_revision=0, action='SetResearchControl',
                payload={'mode': 'LAB_SIMULATION', 'state': 'RUNNING'})
            receipt = await bridge.submit(lease, intent, 'SYNTHETIC_AUTH')
            assert receipt['commit_status'] == 'COMMITTED'
            assert await bridge.submit(lease, intent, 'SYNTHETIC_AUTH') == receipt
            record('commit_and_duplicate', receipt=receipt)
            # Capture actual server term/index/state, not PG epoch or invented votes.
            initial_terms = {}
            for node in nodes:
                stats = (await http.get(endpoint(node) + '/v1/agent/self')).json()['Stats']['raft']
                assert int(stats['term']) > 0 and int(stats['last_log_index']) > 0
                assert int(stats['commit_index']) >= int(stats['applied_index']) > 0
                initial_terms[node['name']] = int(stats['term'])
                record('actual_raft_stats', node=node['name'], stats=stats)
            config = (await http.get(endpoint(nodes[0]) + '/v1/operator/raft/configuration')).json()
            leader_address = next(s['Address'].split(':')[0] for s in config['Servers'] if s['Leader'])
            leader = next(n for n in nodes if n['ip'] == leader_address)
            inspect(leader)
            docker('kill', leader['id'])
            survivors = [n for n in nodes if n is not leader]
            await wait_healthy(http, survivors)
            authority.config = ConsulConfig(endpoints=tuple(endpoint(n) for n in survivors),
                                            namespace=namespace, isolated_lab=True)
            assert await bridge.get_command(intent['command_id'], 'SYNTHETIC_AUTH') == receipt
            record('actual_raft_leader_crash_receipt_survives', node=leader['name'])
            # Current application owner session is explicitly released; no force takeover.
            await authority.release(lease)
            successor = await authority.acquire('PC4')
            assert successor is not None and successor.token > lease.token
            second = dict(intent, command_id=str(uuid.uuid4()), actor_id='lab-human', idempotency_key='second', expected_revision=1,
                          payload={'mode': 'LAB_SIMULATION', 'state': 'PAUSED'})
            assert (await bridge.submit(lease, second, 'SYNTHETIC_AUTH'))['commit_status'] == 'UNKNOWN'
            receipt2 = await bridge.submit(successor, second, 'SYNTHETIC_AUTH')
            assert receipt2['commit_status'] == 'COMMITTED' and receipt2['revision'] == 2
            record('successor_commits_stale_owner_denied', receipt=receipt2)
            victim = survivors[0]
            inspect(victim)
            docker('kill', victim['id'])
            await asyncio.sleep(2)
            third = dict(second, command_id=str(uuid.uuid4()), actor_id='lab-human', idempotency_key='third', expected_revision=2)
            assert (await bridge.submit(successor, third, 'SYNTHETIC_AUTH'))['commit_status'] == 'UNKNOWN'
            record('two_voter_loss_denies_new_command')
            # Kill all processes, retain named volumes, then restart retained IDs.
            for node in nodes:
                if inspect(node)['State']['Running']:
                    docker('kill', node['id'])
            for node in nodes:
                docker('start', node['id'])
            await wait_healthy(http, nodes)
            authority.config = ConsulConfig(endpoints=tuple(endpoint(n) for n in nodes),
                                            namespace=namespace, isolated_lab=True)
            assert await bridge.get_command(intent['command_id'], 'SYNTHETIC_AUTH') == receipt
            assert await bridge.get_command(second['command_id'], 'SYNTHETIC_AUTH') == receipt2
            assert (await bridge.get_command(third['command_id'], 'SYNTHETIC_AUTH'))['commit_status'] == 'UNKNOWN'
            for node in nodes:
                stats = (await http.get(endpoint(node) + '/v1/agent/self')).json()['Stats']['raft']
                assert int(stats['term']) >= initial_terms[node['name']]
                assert int(stats['commit_index']) >= int(stats['applied_index']) > 0
                record('restarted_actual_raft_stats', node=node['name'], stats=stats)
            record('all_process_restart_retained_volumes_receipts_recovered')
            await authority.release(successor)
            minority, majority = nodes[0], nodes[1:]
            isolated_endpoint = endpoint(minority)
            inspect(minority)
            docker('network', 'disconnect', network, minority['id'])
            try:
                await wait_healthy(http, majority)
                minority_authority = ConsulSessionAuthority(ConsulConfig(
                    endpoints=(isolated_endpoint,), namespace=namespace, isolated_lab=True,
                    request_timeout=1), client=http)
                minority_bridge = CoordinationCommands(minority_authority, generation,
                                                       principal_provider=SyntheticLabProvider())
                # An isolated endpoint cannot issue a quorum-backed receipt or
                # publish a new command. UNKNOWN is connectivity, not a forged
                # authenticated assertion of NO_QUORUM.
                assert (await minority_bridge.submit(successor, third, 'SYNTHETIC_AUTH'))['commit_status'] == 'UNKNOWN'
                authority.config = ConsulConfig(endpoints=tuple(endpoint(n) for n in majority),
                                                namespace=namespace, isolated_lab=True)
                assert await bridge.get_command(second['command_id'], 'SYNTHETIC_AUTH') == receipt2
                majority_lease = await authority.acquire('PC3')
                assert majority_lease is not None
                receipt3 = await bridge.submit(majority_lease, third, 'SYNTHETIC_AUTH')
                assert receipt3['commit_status'] == 'COMMITTED'
                record('one_two_network_partition_majority_commits_minority_denied', receipt=receipt3)
            finally:
                docker('network', 'connect', '--alias', minority['name'], network, minority['id'])
            await wait_healthy(http, nodes)
            authority.config = ConsulConfig(endpoints=tuple(endpoint(n) for n in nodes),
                                            namespace=namespace, isolated_lab=True)
            assert await bridge.get_command(third['command_id'], 'SYNTHETIC_AUTH') == receipt3
            await authority.release(majority_lease)
            record('partition_healed_receipts_reconciled_no_forced_failback')
            # Actual Consul snapshot contains FSM plus Raft index/term metadata;
            # inspect it through the pinned vendor CLI and retain its checksum.
            snapshot_node = nodes[0]
            inspect(snapshot_node)
            snapshot_path = '/consul/data/qualification.snap'
            docker('exec', snapshot_node['id'], 'consul', 'snapshot', 'save', snapshot_path)
            snapshot_info = docker('exec', snapshot_node['id'], 'consul', 'snapshot', 'inspect', snapshot_path)
            snapshot_hash = docker('exec', snapshot_node['id'], 'sha256sum', snapshot_path)
            inspect(snapshot_node)
            retained_snapshot = output / 'qualification.snap'
            docker('cp', snapshot_node['id'] + ':' + snapshot_path, str(retained_snapshot))
            if (retained_snapshot.stat().st_size > 16 * 1024**2
                    or hashlib.sha256(retained_snapshot.read_bytes()).hexdigest() != snapshot_hash.split()[0]):
                raise RuntimeError('RETAINED_SNAPSHOT_HASH_OR_BOUND_MISMATCH')
            record('actual_persistent_snapshot', node=snapshot_node['name'],
                   vendor_inspection=snapshot_info, sha256=snapshot_hash.split()[0])
            evidence['result'] = 'PASS'
            record('linux_persistent_command_scenarios_complete', missing=[
                'disk-full/corruption', 'native Windows', 'production mTLS/ACL', 'independent watchdog',
                'SQL cutover', 'physical acceptance', 'snapshot_restore NOT_RUN', 'backup_restore NOT_RUN'])
    except BaseException as exc:
        evidence['result'] = 'FAILED'
        record('failure', error=type(exc).__name__, message=str(exc))
        raise
    finally:
        # Cleanup only exact inspected IDs belonging to this unique fixture.
        for node in nodes:
            try:
                if inspect(node)['State']['Running']:
                    docker('kill', node['id'])
            except Exception as exc:
                record('cleanup_failure', node=node['name'], error=type(exc).__name__)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-isolated-hosted-linux', action='store_true', required=True)
    parser.add_argument('--output', required=True)
    asyncio.run(verify(parser.parse_args().output))
