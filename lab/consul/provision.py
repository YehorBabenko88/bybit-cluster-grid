"""Provision five owned ephemeral Consul Raft voters on the cloud-local daemon."""
import argparse
import json
import ipaddress
import os
from pathlib import Path
import subprocess
import uuid

IMAGE = 'hashicorp/consul@sha256:259fd02f2544fe1aa03fa49efd3b105c8dd67106d710a72f5e898110266356f7'


def docker(*args):
    env = os.environ.copy()
    for name in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        env.pop(name, None)
    return subprocess.check_output(['docker', '--host=unix:///var/run/docker.sock', *args], env=env, text=True).strip()


def provision(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    label = 'mission3-consul-' + uuid.uuid4().hex[:12]
    network = label + '-net'
    names = [label + '-v' + str(i) for i in range(1, 6)]
    network_ids = docker('network', 'ls', '-q').splitlines()
    existing = json.loads(docker('network', 'inspect', *network_ids)) if network_ids else []
    occupied = [ipaddress.ip_network(c['Subnet']) for n in existing for c in (n['IPAM'].get('Config') or []) if c.get('Subnet')]
    candidates = (ipaddress.ip_network('172.30.' + str(i) + '.0/24') for i in range(256))
    subnet = next((candidate for candidate in candidates if not any(candidate.overlaps(n) for n in occupied if n.version == 4)), None)
    if subnet is None:raise RuntimeError('no free cloud lab subnet')
    docker('network', 'create', '--internal', '--subnet', str(subnet), '--label', 'grid.lab=' + label, network)
    network_info = json.loads(docker('network', 'inspect', network))[0]
    subnet = ipaddress.ip_network(next(c['Subnet'] for c in network_info['IPAM']['Config'] if ':' not in c['Subnet']))
    manifest = {'schema': 'grid.consul.disposable-lab.v1', 'label': label, 'network': network,
                'image': IMAGE, 'voters': [], 'scope': 'CLOUD_DISPOSABLE_ONLY', 'production_security': 'NOT_QUALIFIED'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    for index, name in enumerate(names):
        args = ['run', '-d', '--name', name, '--hostname', name, '--network', network,
                '--ip', str(subnet.network_address + index + 2),
                '--label', 'grid.lab=' + label, '--label', 'grid.lab.role=consul-voter',
                '-e', 'CONSUL_LOCAL_CONFIG=' + json.dumps({'autopilot': {'cleanup_dead_servers': False}, 'leave_on_terminate': False}),
                '--memory', '256m', '--cpus', '0.5', '--restart=no', IMAGE,
                'agent', '-server', '-bootstrap-expect=5', '-node=' + name, '-client=0.0.0.0',
                '-bind=0.0.0.0', '-retry-interval=1s', '-data-dir=/consul/data']
        for peer in names:
            if peer != name:
                args.append('-retry-join=' + peer)
        container_id = docker(*args)
        info = json.loads(docker('inspect', container_id))[0]
        ip = info['NetworkSettings']['Networks'][network]['IPAddress']
        manifest['voters'].append({'name': name, 'id': container_id, 'ip': ip,
                                   'endpoint': 'http://' + ip + ':8500'})
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-isolated-cloud-lab', action='store_true', required=True)
    parser.add_argument('--output', required=True)
    provision(parser.parse_args().output)
