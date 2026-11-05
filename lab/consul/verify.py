"""Real cloud-only Raft fault matrix; mutates only manifest-bound labelled lab IDs."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import httpx
from grid.coordination import ConsulConfig, ConsulSessionAuthority, CoordinationLost, CoordinationUnavailable
from provision import docker, IMAGE

TOOL = 'nicolaka/netshoot@sha256:7f08c4aff13ff61a35d30e30c5c1ea8396eac6ab4ce19fd02d5a4b3b5d0d09a2'


def checked(manifest, voter, *, refresh_address=False):
    if (manifest['image'] != IMAGE or not manifest['label'].startswith('mission3-consul-')
            or manifest['network'] != manifest['label'] + '-net'):
        raise ValueError('LAB_MANIFEST_IDENTITY_MISMATCH')
    info = json.loads(docker('inspect', voter['id']))[0]
    if (info['Id'] != voter['id'] or info['Name'] != '/' + voter['name']
            or info['Config']['Labels'].get('grid.lab') != manifest['label']
            or info['Config']['Labels'].get('grid.lab.role') != 'consul-voter'
            or info['Config']['Image'] != manifest['image']
            or info['HostConfig']['RestartPolicy']['Name'] != 'no'):
        raise ValueError('LAB_IDENTITY_MISMATCH')
    address = info['NetworkSettings']['Networks'][manifest['network']]['IPAddress']
    if refresh_address and address:
        # IDs, image, labels and the internal network were verified above.
        # Docker may reassign an owned address after an abrupt stop/start.
        voter['ip'] = address
        voter['endpoint'] = 'http://' + address + ':8500'
    if (address != voter['ip'] or voter['endpoint'] != 'http://' + address + ':8500'):
        raise ValueError('LAB_ENDPOINT_IDENTITY_MISMATCH')
    network = json.loads(docker('network', 'inspect', manifest['network']))[0]
    if not network['Internal'] or network['Labels'].get('grid.lab') != manifest['label']:
        raise ValueError('LAB_NETWORK_IDENTITY_MISMATCH')
    return info


def firewall(manifest, voter, destination, operation):
    checked(manifest, voter)
    # iptables runs in this owned container's network namespace, never the host.
    docker('run', '--rm', '--network', 'container:' + voter['id'], '--cap-add=NET_ADMIN',
           '--label', 'grid.lab=' + manifest['label'], '--label', 'grid.lab.role=fault-injector',
           TOOL, 'iptables', operation, 'OUTPUT', '-d', destination['ip'], '-j', 'DROP')


async def verify(path):
    path = Path(path)
    m = json.loads((path / 'manifest.json').read_text())
    if m['scope'] != 'CLOUD_DISPOSABLE_ONLY' or len(m['voters']) != 5:
        raise ValueError('LAB_SCOPE_REQUIRED')
    for v in m['voters']: checked(m, v, refresh_address=True)
    (path / 'observed-manifest.json').write_text(json.dumps(m, indent=2))
    events = []
    def record(name, **values):
        events.append({'scenario': name, **values})
        (path / 'raft-evidence.json').write_text(json.dumps({'schema': 'grid.consul.raft-lab.v1',
            'manifest': m, 'events': events, 'physical_windows': 'NOT_RUN', 'production_tls_acl': 'NOT_RUN'}, indent=2))
    async with httpx.AsyncClient(trust_env=False) as http:
        async def raft(voters):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                for v in voters:
                    try:
                        r = await http.get(v['endpoint'] + '/v1/operator/raft/configuration', timeout=.7)
                        r.raise_for_status()
                        p = r.json()
                        if len(p['Servers']) == 5 and all(s['Voter'] for s in p['Servers']):
                            return p
                    except (httpx.HTTPError, KeyError): pass
                await asyncio.sleep(.25)
            raise RuntimeError('five-voter Raft configuration unavailable')
        async def eventually(operation, seconds=30):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                try:
                    result = await operation()
                    if result is not None and result is not False:return result
                except CoordinationUnavailable:pass
                await asyncio.sleep(.3)
            raise RuntimeError('bounded quorum operation did not recover')
        def authority(voters, namespace, ttl=120):
            return ConsulSessionAuthority(ConsulConfig(endpoints=tuple(v['endpoint'] for v in voters),
                namespace=namespace, isolated_lab=True, ttl_seconds=ttl), client=http)
        baseline = await raft(m['voters'])
        record('five-real-voters', raft=baseline)
        api = authority(m['voters'], 'lab-grid/fault-matrix')
        lease = await api.acquire('node-a')
        await api.write_control(lease, 'placements', {'job': 'node-a', 'generation': 1})
        leader = next(s for s in baseline['Servers'] if s['Leader'])
        first = next(v for v in m['voters'] if v['name'] == leader['Node'])
        second = next(v for v in m['voters'] if v != first)
        crashed = []
        try:
            for count, voter in enumerate((first, second), 1):
                checked(m, voter)
                docker('kill', '--signal=KILL', voter['id'])
                crashed.append(voter)
                live = [v for v in m['voters'] if v not in crashed]
                current = await raft(live)
                assert await eventually(lambda: api.renew(lease))
                await api.write_control(lease, 'placements', {'job': 'node-a', 'generation': count + 1})
                stored = await api.read_control('placements')
                assert stored['payload']['generation'] == count + 1
                record('loss-' + str(count), stopped=[v['id'] for v in crashed], raft=current,
                       token=lease.token, durable_record=stored)
        finally:
            for voter in crashed: docker('start', voter['id'])
        for v in m['voters']:checked(m, v, refresh_address=True)
        (path / 'observed-manifest.json').write_text(json.dumps(m, indent=2))
        await raft(m['voters'])
        await api.release(lease)
        record('crashed-voters-restored', raft=await raft(m['voters']))
        minority = m['voters'][:2]
        majority = m['voters'][2:]
        old = authority(minority[:1], 'lab-grid/partition', ttl=10)
        new = authority(majority, 'lab-grid/partition', ttl=10)
        oldlease = await eventually(lambda: old.acquire('minority-owner'))
        await old.write_control(oldlease, 'placements', {'job': 'minority-owner'})
        rules = []
        try:
            for source in minority:
                for destination in majority:
                    firewall(m, source, destination, '-I')
                    rules.append((source, destination))
            assert await old.renew(oldlease) is False
            assert await old.validate(oldlease) is False
            try:
                await old.write_control(oldlease, 'placements', {'job': 'stale-minority'})
            except CoordinationLost: pass
            else: raise AssertionError('minority write must be fenced')
            replacement = await eventually(lambda: new.acquire('majority-owner'), seconds=40)
            assert replacement.token > oldlease.token
            await new.write_control(replacement, 'placements', {'job': 'majority-owner'})
            stored = await new.read_control('placements')
            assert stored['owner'] == 'majority-owner'
            record('two-versus-three-partition', minority=[v['id'] for v in minority],
                   majority=[v['id'] for v in majority], old_token=oldlease.token,
                   new_token=replacement.token, durable_record=stored,
                   injection='network-namespace OUTPUT drop between minority and majority; intra-minority traffic allowed')
        finally:
            for source, destination in reversed(rules):firewall(m, source, destination, '-D')
        await raft(m['voters'])
        assert await old.validate(oldlease) is False
        try:
            await old.write_control(oldlease, 'placements', {'job': 'stale-after-heal'})
        except CoordinationLost: pass
        else: raise AssertionError('old token must remain fenced after healing')
        # Prove the replicated server itself rejects a stale transaction,
        # independently of our client's conservative local TTL rejection.
        stale_ops = [
            {'KV': {'Verb': 'check-session', 'Key': new.key, 'Session': oldlease.session_id}},
            {'KV': {'Verb': 'check-index', 'Key': new.key, 'Index': oldlease.token}},
            {'KV': {'Verb': 'set', 'Key': new.config.namespace + '/state/placements',
                    'Value': base64.b64encode(b'{"owner":"stale-raw-writer"}').decode()}},
        ]
        denied = await http.put(majority[0]['endpoint'] + '/v1/txn', json=stale_ops, timeout=2)
        assert denied.status_code == 409 and denied.json()['Errors']
        assert (await new.read_control('placements'))['owner'] == 'majority-owner'
        record('server-atomic-stale-session-and-index-rejected', http_status=denied.status_code)
        await new.release(replacement)
        successor = await eventually(lambda: new.acquire('reassigned-owner'))
        assert successor.token > replacement.token
        await new.write_control(successor, 'placements', {'job': 'reassigned-owner'})
        assert (await new.read_control('placements'))['owner'] == 'reassigned-owner'
        await new.release(successor)
        record('healed-stale-token-rejected-and-work-reassigned', old_token=oldlease.token,
               successor_token=successor.token, raft=await raft(m['voters']))
        # Prove no unlabelled resource or physical endpoint was a test target.
        for v in m['voters']:
            assert checked(m, v)['State']['Running']
            observer = authority([v], new.config.namespace)
            visible = await eventually(lambda: observer.read_control('placements'))
            assert visible['owner'] == 'reassigned-owner'
        record('restored-five-voters', result='PASS')
        print(json.dumps({'result': 'PASS', 'events': len(events), 'evidence': str(path / 'raft-evidence.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-isolated-cloud-lab', action='store_true', required=True)
    parser.add_argument('--evidence', required=True)
    asyncio.run(verify(parser.parse_args().evidence))
