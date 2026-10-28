"""Explicit hosted component fixtures, never a physical S0 attestation.

No sockets or Win32 calls are made unless the genuine hosted-job gate passes.
Fixtures use loopback, synthetic market data, and owned temporary resources.
"""
import os
import sys

import pytest

if os.environ.get('S0_HOSTED_TESTS') != '1':
    pytest.skip('hosted component fixtures are opt-in', allow_module_level=True)
if not (
    os.environ.get('GITHUB_ACTIONS') == 'true'
    and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
    and os.environ.get('GITHUB_REPOSITORY') == 'YehorBabenko88/bybit-cluster-grid'
    and os.environ.get('GITHUB_JOB') in ('s0-windows', 's0-linux')
):
    raise RuntimeError('S0_HOSTED_TESTS requires the designated genuine GitHub hosted job')

import asyncio
import socket
import ssl
import time
import uuid
from pathlib import Path
from decimal import Decimal

from aiohttp import web
from s0_smoke import materials, runtime
from s0_smoke.policy import load_json
from s0_smoke.storage import Journal, write_new
from s0_smoke.policy import canonical


def fixture_plan(port):
    return dict(schema=1, profile='PHYSICAL_SMOKE_S0', head=os.environ['EXACT_HEAD_SHA'],
                run_id=str(uuid.uuid4()), duration_seconds=300, symbol='BTCUSDT',
                bybit_url='wss://stream.bybit.com/v5/public/linear',
                coordinator_ip='127.0.0.1', worker_ip='127.0.0.1', port=port,
                operator_sids={'LS5':'S-1-5-21-1-2-3-1001', 'PC4':'S-1-5-21-4-5-6-1001'})


def test_hosted_mtls_market_component_fixture(tmp_path, monkeypatch):
    asyncio.run(_component_fixture(tmp_path, monkeypatch))


async def _component_fixture(tmp_path, monkeypatch):
    # The reservation only selects a fixture port; production policy still rejects it.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    plan = fixture_plan(port)
    with monkeypatch.context() as scope:
        scope.setattr(materials, 'validate_plan', lambda *_: None)
        generated = materials.materials(plan, plan['head'], 'b'*64)
    with pytest.raises(ValueError):
        materials.validate_config(generated['LS5']['config.json'], plan['head'], 'b'*64)
    canary = tmp_path / 'outside-canary.bin'
    canary.write_bytes(b'fixture-external-canary')
    roots, configs, journals = {}, {}, {}
    for role in ('LS5', 'PC4'):
        root = tmp_path / role; root.mkdir()
        roots[role] = root
        for name, data in generated[role].items():
            write_new(root, name, data)
        configs[role] = load_json(generated[role]['config.json'])
        materials.tls_context(configs[role], root)
        context = dict(head=plan['head'], run_id=plan['run_id'], role=role)
        write_new(root, 'claim.json', canonical(dict(context, fixture=True, pid=os.getpid(),
            github_run_id=os.environ['GITHUB_RUN_ID'], github_run_attempt=os.environ['GITHUB_RUN_ATTEMPT'])))
        journals[role] = Journal(root, 'events.jsonl', context)
        journals[role].add('started', {'fixture': True})
    market = Journal(roots['PC4'], 'market.jsonl', dict(head=plan['head'], run_id=plan['run_id'], role='PC4'))
    connections = 0

    async def feed(request):
        nonlocal connections
        connections += 1
        connection = connections
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        subscription = await ws.receive_json(timeout=2)
        assert subscription['op'] == 'subscribe'
        assert subscription['args'] == ['orderbook.1.BTCUSDT', 'publicTrade.BTCUSDT']
        await ws.send_json({'op': 'subscribe', 'req_id': 'S0', 'success': True})
        for n in range(20):
            now = int(time.time()*1000)
            await ws.send_json(dict(topic='orderbook.1.BTCUSDT', type='snapshot', ts=now,
                cts=now, data=dict(s='BTCUSDT', b=[['60000','1']], a=[['60001','1']], u=n+2, seq=n+10)))
            # The first ID is replayed unchanged after reconnect, including timestamp.
            if n == 0:
                trade = replay
            else:
                trade = dict(T=now, s='BTCUSDT', S='Buy', v='0.01', p='60000',
                             i=f'{connection}-{n}', BT=False, seq=n+10)
            await ws.send_json(dict(topic='publicTrade.BTCUSDT', type='snapshot', ts=now, data=[trade]))
            if connection == 1 and n == 1:
                await ws.close(); return ws
            await asyncio.sleep(.08)
        await ws.close()
        return ws

    replay = dict(T=int(time.time()*1000), s='BTCUSDT', S='Buy', v='0.01',
                  p='60000', i='replayed-across-connections', BT=False, seq=10)
    app = web.Application(); app.router.add_get('/fixture-feed', feed)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    feed_port = site._server.sockets[0].getsockname()[1]

    async def fixture_connection(session):
        return await session.ws_connect(f'http://127.0.0.1:{feed_port}/fixture-feed', heartbeat=None)

    monkeypatch.setattr(runtime, 'public_connection', fixture_connection)
    try:
        co = asyncio.create_task(runtime.coordinator(configs['LS5'], roots['LS5'], journals['LS5'], lambda: None, seconds=3))
        await asyncio.sleep(.15)
        wo = asyncio.create_task(runtime.worker(configs['PC4'], roots['PC4'], journals['PC4'], market, lambda: None, seconds=3))
        coordinator_result, worker_result = await asyncio.wait_for(asyncio.gather(co, wo), timeout=12)
        assert coordinator_result['reason'] == 'WINDOW_COMPLETE'
        assert worker_result['reason'] == 'WINDOW_COMPLETE'
        assert coordinator_result['registered']
        assert coordinator_result['heartbeats'] > 0
        assert worker_result['registered']
        assert worker_result['heartbeats'] > 0
        stats = worker_result['stats']
        assert stats['book_updates'] > 0
        assert stats['trade_count'] > 0
        assert stats['reconnects'] >= 1
        assert stats['duplicate_trades'] >= 1
        assert Decimal(stats['buy_volume']) == Decimal(stats['trade_count']) * Decimal('0.01')
        assert canary.read_bytes() == b'fixture-external-canary'
        for role, result in (('LS5', coordinator_result), ('PC4', worker_result)):
            journals[role].add('finished', {'result': result, 'error': None})
    finally:
        for task in (locals().get('co'), locals().get('wo')):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (locals().get('co'), locals().get('wo')) if t is not None), return_exceptions=True)
        await runner.cleanup()
        market.close()
        for journal in journals.values(): journal.close()
    from s0_smoke.cli import finish
    from s0_smoke.evidence import verify_evidence
    for role, result in (('LS5', coordinator_result), ('PC4', worker_result)):
        root = roots[role]
        summary = finish(root, configs[role], result, None, {'tree': os.environ['EXACT_TREE_SHA']}, 'b'*64)
        assert summary['status'] == 'BLOCKED_OR_PARTIAL'
        context = dict(head=plan['head'], run_id=plan['run_id'], role=role)
        checked = verify_evidence(root, context, 'b'*64)
        assert checked['status'] == 'S0_EVIDENCE_CONSISTENT_NOT_ATTESTED'
        destination = Path(__file__).resolve().parents[1] / 's0-results' / 'component-fixture' / role
        destination.mkdir(parents=True, exist_ok=False)
        for name in ('events.jsonl', 'market.jsonl', 'claim.json', 'summary.json', 'results.xml', 'sha256.json'):
            if (root / name).is_file():
                write_new(destination, name, (root / name).read_bytes())
        assert verify_evidence(destination, context, 'b'*64)['observation'] == 'BLOCKED_OR_PARTIAL'


@pytest.mark.skipif(sys.platform != 'win32', reason='native owned-resource fixture requires Windows')
def test_hosted_windows_native_owned_custody():
    from s0_smoke.windows import current_identity, create_fresh_root, create_fresh_file, Custody, Win32, diagnostic_observation
    identity = current_identity()  # Read-only token query; admin runner is not standard-token evidence.
    assert identity.sid.startswith('S-1-')
    from tools.build_s0_package import hosted_local_app_data
    root = hosted_local_app_data() / ('s0-native-owned-' + str(uuid.uuid4()))
    # Preserve actual ancestor facts on rejection, without changing the policy or ACL.
    import json
    api = Win32()
    observations = []
    for parent in reversed(root.parents):
        handle = api.open(str(parent), True)
        try:
            observations.append(diagnostic_observation(str(parent), api.inspect(handle)))
        finally:
            api.close(handle)
    print('S0_HOSTED_ANCESTORS=' + json.dumps(observations, sort_keys=True))
    create_fresh_root(root, identity.sid)
    file = root / 'fixture.bin'
    create_fresh_file(file, identity.sid, b'owned fixture')
    with Custody(root, identity.sid, [file]) as custody:
        custody.guard()
        assert file.read_bytes() == b'owned fixture'
    # No removal or existing ACL changes: the disposable hosted VM owns cleanup.


def test_hosted_mtls_rejects_client_without_certificate(tmp_path, monkeypatch):
    asyncio.run(_reject_uncredentialed_client(tmp_path, monkeypatch))


async def _reject_uncredentialed_client(tmp_path, monkeypatch):
    import aiohttp
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
    plan = fixture_plan(port)
    with monkeypatch.context() as scope:
        scope.setattr(materials, 'validate_plan', lambda *_: None)
        generated = materials.materials(plan, plan['head'], 'b'*64)
    root = tmp_path / 'server'; root.mkdir()
    for name, data in generated['LS5'].items(): write_new(root, name, data)
    config = load_json(generated['LS5']['config.json'])
    context = dict(head=plan['head'], run_id=plan['run_id'], role='LS5')
    with Journal(root, 'events.jsonl', context) as journal:
        server = asyncio.create_task(runtime.coordinator(config, root, journal, lambda: None, seconds=1))
        await asyncio.sleep(.15)
        # Trust the correct server CA but deliberately supply no client credential.
        client = ssl.create_default_context(cafile=str(root / 'ca.pem'))
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1)) as session:
                with pytest.raises((aiohttp.ClientError, TimeoutError)):
                    async with session.post(f'https://127.0.0.1:{port}/s0', ssl=client, json={}) as response:
                        await response.read()
            result = await asyncio.wait_for(server, timeout=3)
            assert result['registered'] is False
            assert result['heartbeats'] == 0
        finally:
            if not server.done(): server.cancel()
            await asyncio.gather(server, return_exceptions=True)


def test_hosted_tls_material_rejects_forged_role(tmp_path, monkeypatch):
    plan = fixture_plan(49441)
    with monkeypatch.context() as scope:
        scope.setattr(materials, 'validate_plan', lambda *_: None)
        generated = materials.materials(plan, plan['head'], 'b'*64)
    root = tmp_path / 'forged'; root.mkdir()
    for name, data in generated['LS5'].items(): write_new(root, name, data)
    config = load_json(generated['LS5']['config.json'])
    config['role'] = 'PC4'  # Hashes remain valid; explicit signed role URN must fail.
    with pytest.raises(ValueError): materials.tls_context(config, root)
