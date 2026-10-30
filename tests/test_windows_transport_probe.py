"""Offline fault tests. No real sockets, hosts, processes, or native APIs."""
import copy
import json
import socket

import pytest

from integration import windows_transport_probe as probe


def config():
    return dict(schema=1, head='a'*40, run_id='12', attempt='1', nonce='b'*32,
                parent_pid=123, endpoints=[
                    ['IPv4', '127.0.0.1', 12001, 'listener'],
                    ['IPv4', '127.0.0.1', 12002, 'bound-not-listening'],
                    ['IPv6', '::1', 12003, 'listener'],
                    ['IPv6', '::1', 12004, 'bound-not-listening']])


@pytest.mark.parametrize('change', [
    lambda c: c.update(schema=True), lambda c: c.update(head='a'*39),
    lambda c: c.update(parent_pid=True), lambda c: c.update(nonce='b'*31),
    lambda c: c.update(run_id='0'), lambda c: c.update(attempt=1),
    lambda c: c.update(external=['example.com', 443]),
    lambda c: c['endpoints'][0].__setitem__(1, '127.0.0.2'),
    lambda c: c['endpoints'][0].__setitem__(2, True),
    lambda c: c['endpoints'].__setitem__(1, c['endpoints'][0]),
    lambda c: c['endpoints'].pop(),
])
def test_config_rejects_substitution_and_type_confusion(change):
    cfg = config(); change(cfg)
    with pytest.raises(ValueError): probe.validate_config(cfg)


def test_config_is_copied_and_external_destinations_cannot_be_configured():
    cfg = config(); before = copy.deepcopy(cfg)
    endpoints = probe.targets(probe.validate_config(cfg))
    assert cfg == before
    assert endpoints[-2:] == [('IPv4', '192.0.2.1', 9, 'external'),
                              ('IPv6', '2001:db8::1', 9, 'external')]


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError): probe.parse_config('{"schema":1,"schema":1}')


class Clock:
    def __init__(self): self.value = 0
    def __call__(self): return self.value


class Client:
    def __init__(self, initial=10035, final=10013, peer=('127.0.0.1', 12001), local_error=False):
        self.initial, self.final, self.peer = initial, final, peer
        self.local_error = local_error; self.error_reads = 0; self.closed = False
    def setblocking(self, value): assert value is False
    def bind(self, endpoint): self.bound = endpoint
    def connect_ex(self, endpoint): self.destination = endpoint; return self.initial
    def getsockopt(self, *args): self.error_reads += 1; return self.final
    def getpeername(self): return self.peer
    def getsockname(self):
        if self.local_error: raise OSError(10022, 'local unavailable')
        return ('127.0.0.1', 40000)
    def close(self): self.closed = True


def attempt(client, ready=True):
    clock = Clock()
    def poll(read, write, exceptional, timeout):
        clock.value += timeout
        return (read, write, exceptional) if ready else ([], [], [])
    return probe.observe_attempt(('IPv4', '127.0.0.1', 12001, 'listener'),
                                 socket_factory=lambda *args: client, poll=poll,
                                 clock=clock, utc_ms=lambda: 10)


@pytest.mark.parametrize('raw,classification', [(10013, 'ERROR10013'), (10061, 'ERROR10061'),
                                               (10051, 'OTHER_ERROR')])
def test_pending_completion_keeps_initial_and_final_raw_codes(raw, classification):
    client = Client(final=raw)
    row = attempt(client)
    assert row['initial_code'] == 10035
    assert row['so_error'] == raw
    assert row['classification'] == classification
    assert row['evidence'] == 'UNKNOWN'
    assert row['poll_trace'][0] == dict(elapsed_ms=100, readable=True, writable=True, exceptional=True)
    assert client.error_reads == 1 and client.closed


def test_timeout_never_reads_so_error_or_silently_calls_zero_success():
    client = Client(final=0)
    row = attempt(client, ready=False)
    assert row['classification'] == 'TIMEOUT'
    assert row['so_error'] is None
    assert client.error_reads == 0
    assert row['elapsed_ms'] == 6000 and len(row['poll_trace']) <= 80


@pytest.mark.parametrize('initial', [0, 10035])
def test_unexpected_connection_survives_local_endpoint_failure(initial):
    client = Client(initial=initial, final=0, local_error=True)
    row = attempt(client)
    assert row['classification'] == 'UNEXPECTED_CONNECTION'
    assert row['connected'] is True
    assert row['local_endpoint'] is None
    assert row['local_error']['errno'] == 10022
    assert row['peer_endpoint'] == ['127.0.0.1', 12001]


def test_zero_without_expected_peer_is_unknown():
    row = attempt(Client(final=0, peer=('127.0.0.1', 9999)))
    assert row['classification'] == 'PEER_MISMATCH'
    assert row['connected'] is False
    assert row['evidence'] == 'UNKNOWN'


def test_immediate_refusal_does_not_read_so_error():
    client = Client(initial=10061)
    row = attempt(client)
    assert row['classification'] == 'ERROR10061' and client.error_reads == 0


def test_outbound_attempt_uses_implicit_os_binding_without_calling_bind():
    class ImplicitOnlyClient(Client):
        def bind(self, endpoint): raise AssertionError('outbound bind changes baseline')
    client = ImplicitOnlyClient(initial=0, local_error=True)
    row = attempt(client)
    assert row['bind_policy'] == 'IMPLICIT_OS_SELECTED'
    assert row['classification'] == 'UNEXPECTED_CONNECTION' and row['connected'] is True
    assert row['local_endpoint'] is None and row['local_error']['errno'] == 10022


def test_trace_budget_exhaustion_does_not_claim_complete_timeout():
    client = Client()
    row = probe.observe_attempt(('IPv4', '127.0.0.1', 12001, 'listener'),
        socket_factory=lambda *args: client, poll=lambda *args: ([], [], []),
        clock=lambda: 0, utc_ms=lambda: 10)
    assert len(row['poll_trace']) == 80
    assert row['classification'] == 'TRACE_LIMIT' and row['complete'] is False
    assert client.error_reads == 0


@pytest.mark.parametrize('code,classification', [(10013, 'ERROR10013'), (10061, 'ERROR10061')])
def test_exception_error_codes_remain_raw_and_are_classified(code, classification):
    class FaultClient(Client):
        def connect_ex(self, endpoint): raise OSError(code, 'injected')
    row = attempt(FaultClient())
    assert row['error']['errno'] == code
    assert row['initial_code'] is None and row['so_error'] is None
    assert row['classification'] == classification and row['evidence'] == 'UNKNOWN'


def test_os_timeout_exception_is_timeout_without_a_fabricated_wsa_code():
    class FaultClient(Client):
        def connect_ex(self, endpoint): raise TimeoutError('injected')
    row = attempt(FaultClient())
    assert row['classification'] == 'TIMEOUT'
    assert row['error']['winerror'] is None and row['initial_code'] is None


def test_six_attempts_continue_after_independent_exception():
    visited = []
    def observe(target):
        visited.append(target)
        if len(visited) == 1: raise OSError(10013, 'denied')
        return dict(complete=True, evidence='UNKNOWN', classification='TIMEOUT')
    result = probe.run_probe(config(), observe=observe,
                             controls=lambda: [dict(complete=True)]*3,
                             pid=456, isolated=True, grid_modules=[])
    assert len(visited) == 6 and len(result['attempts']) == 6
    assert result['status'] == 'BLOCKED'
    assert result['execution_authorized'] is False
    assert result['cleanup_authorized'] is False
    assert result['physical_status'] == '0/10 NOT_RUN'


def test_completed_observations_never_attest_or_authorize():
    result = probe.run_probe(config(), observe=lambda target: dict(complete=True, evidence='UNKNOWN'),
                             controls=lambda: [dict(complete=True)]*3,
                             pid=456, isolated=True, grid_modules=[])
    assert result['status'] == 'OBSERVED_NOT_ATTESTED'
    assert result['head'] == 'a'*40 and result['nonce'] == 'b'*32
    assert result['readiness_passed'] is False and result['physical_ready'] is False
    assert result['host_verified'] is False and result['verified_safety_cases'] == 0


@pytest.mark.parametrize('platform,isolated,host', [('linux', True, 'runner'),
    ('win32', False, 'runner'), ('win32', True, 'LS5'), ('win32', True, 'PC4')])
def test_native_gate_refuses_wrong_platform_isolation_or_physical_host(platform, isolated, host):
    root = 'C:/Users/runner/AppData/Local/Packages/g1-fixture-11111111-1111-4111-8111-111111111111/AC/python-22222222-2222-4222-8222-222222222222'
    with pytest.raises(ValueError):
        probe.native_scope(root, host, ['--native-child'], platform, isolated)


class ExchangeChannel:
    def __init__(self, address):
        self.address = address; self.buffer = b''; self.closed = False
    def settimeout(self, seconds): assert 0 < seconds <= 6
    def getsockname(self): return self.address
    def getpeername(self): return self.peer.address
    def sendall(self, data): self.peer.buffer += data
    def recv(self, size):
        # Fragmented reads exercise the exact-length exchange loop.
        part = self.buffer[:min(size, 2)]; self.buffer = self.buffer[len(part):]
        return part
    def close(self): self.closed = True


def fake_controls(fail_family=None, corrupt=False):
    held = []; listeners = {}
    def pair():
        left = ExchangeChannel(('local', 1)); right = ExchangeChannel(('local', 2))
        left.peer = right; right.peer = left; held.extend((left, right))
        return left, right
    class TCP(ExchangeChannel):
        def __init__(self, family):
            super().__init__(None); self.family = family; held.append(self)
        def bind(self, endpoint):
            if self.family == fail_family: raise OSError(10013, 'injected bind failure')
            self.address = (endpoint[0], 12345)
        def listen(self, count): listeners[self.family] = self
        def connect(self, endpoint):
            self.address = (endpoint[0], 40000)
            self.peer = ExchangeChannel(endpoint); self.peer.peer = self; held.append(self.peer)
            listeners[self.family].accepted = self.peer
        def accept(self): return self.accepted, self.accepted.getpeername()
        def sendall(self, data): super().sendall(b'corrupt!' if corrupt else data)
    rows = probe.self_controls(socket_factory=lambda family, kind: TCP(family),
                               pair_factory=pair, clock=lambda: 0)
    return rows, held


def test_self_controls_exchange_bounded_bytes_on_both_families_and_socketpair():
    rows, held = fake_controls()
    assert [row['name'] for row in rows] == ['IPv4', 'IPv6', 'socketpair']
    assert all(row['complete'] is True for row in rows)
    assert all(channel.closed for channel in held)
    assert all(row['evidence'] == 'UNKNOWN' for row in rows)


def test_control_failure_does_not_skip_other_family_or_socketpair():
    rows, held = fake_controls(fail_family=socket.AF_INET)
    assert [row['complete'] for row in rows] == [False, True, True]
    assert rows[0]['error']['errno'] == 10013
    assert all(channel.closed for channel in held)


def test_self_control_corrupt_data_cannot_count_as_completed_exchange():
    rows, held = fake_controls(corrupt=True)
    assert [row['complete'] for row in rows] == [False, False, True]
    assert all(channel.closed for channel in held)


def test_native_gate_accepts_only_exact_owned_profile_shape():
    root = 'C:/Users/runner/AppData/Local/Packages/g1-fixture-11111111-1111-4111-8111-111111111111/AC/python-22222222-2222-4222-8222-222222222222'
    probe.native_scope(root, 'runner', ['--native-child'], 'win32', True)
    for changed in (root.replace('/AC/', '/Data/'), root.replace('g1-fixture-', 'foreign-'),
                    root.replace('python-', 'other-')):
        with pytest.raises(ValueError):
            probe.native_scope(changed, 'runner', ['--native-child'], 'win32', True)


def test_write_result_uses_existing_empty_parent_retained_file_once(tmp_path):
    (tmp_path / 'Data').mkdir(); path = tmp_path / 'Data' / 'result.json'
    path.write_bytes(b'')
    result = {'status': 'BLOCKED', 'execution_authorized': False}
    probe.write_result(tmp_path, result)
    assert path.read_bytes() == b'{"execution_authorized":false,"status":"BLOCKED"}'
    with pytest.raises(ValueError): probe.write_result(tmp_path, result)
    assert json.loads(path.read_bytes()) == result


def test_write_result_refuses_missing_file_without_creating_one(tmp_path):
    (tmp_path / 'Data').mkdir()
    with pytest.raises(FileNotFoundError): probe.write_result(tmp_path, {})
    assert not (tmp_path / 'Data' / 'result.json').exists()


@pytest.mark.parametrize('result', [{'x': 'x'*65536}, {'x': float('nan')}])
def test_write_result_invalid_or_oversized_output_leaves_retained_file_empty(tmp_path, result):
    (tmp_path / 'Data').mkdir(); path = tmp_path / 'Data' / 'result.json'; path.write_bytes(b'')
    with pytest.raises(ValueError): probe.write_result(tmp_path, result)
    assert path.read_bytes() == b''


def test_write_result_refuses_multiple_links_to_retained_slot(tmp_path):
    (tmp_path / 'Data').mkdir(); path = tmp_path / 'Data' / 'result.json'; path.write_bytes(b'')
    (tmp_path / 'alias.json').hardlink_to(path)
    with pytest.raises(ValueError): probe.write_result(tmp_path, {'status': 'BLOCKED'})
    assert path.read_bytes() == b''


def test_nonempty_result_slot_is_preserved(tmp_path):
    (tmp_path / 'Data').mkdir(); path = tmp_path / 'Data' / 'result.json'
    path.write_bytes(b'parent retained contents')
    with pytest.raises(ValueError): probe.write_result(tmp_path, {'status': 'BLOCKED'})
    assert path.read_bytes() == b'parent retained contents'
