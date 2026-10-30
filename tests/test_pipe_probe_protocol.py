"""Pure framing/fault tests; never execute native APIs or actual pipes."""
import json

import pytest

from integration import pipe_probe_protocol as protocol
from integration import windows_pipe_probe as child


def context():
    return dict(head='a'*40, run_id='12', attempt='1', nonce='b'*32, pid=456)


def config():
    return dict(schema=1, head='a'*40, run_id='12', attempt='1', nonce='b'*32,
                parent_pid=123, canary='C:/synthetic-fixture/outside.fixture')


def frame(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('ascii')
    return len(raw).to_bytes(4, 'little') + raw


def test_fixed_ping_round_trip_has_only_context_and_no_authority():
    expected = context()
    raw = protocol.encode_ping(expected)
    result = protocol.validate_frame(raw, expected)
    assert result == dict(schema=1, verb='ping', **expected)
    assert len(raw) <= 516
    assert raw[4:] == json.dumps(result, sort_keys=True, separators=(',', ':')).encode('ascii')


@pytest.mark.parametrize('mutation', [lambda p: p.update(verb='exec'),
    lambda p: p.update(action='cleanup'), lambda p: p.update(path='C:/foreign'),
    lambda p: p.update(schema=True), lambda p: p.update(pid=True),
    lambda p: p.update(nonce='c'*32), lambda p: p.update(head='c'*40),
    lambda p: p.update(run_id='13'), lambda p: p.update(attempt='2'),
    lambda p: p.update(pid=789), lambda p: p.update(verb={'nested': 'ping'}),
    lambda p: p.update(pid=float('nan'))])
def test_frame_rejects_promotion_and_cross_context_replay(mutation):
    payload = dict(schema=1, verb='ping', **context()); mutation(payload)
    with pytest.raises(ValueError): protocol.validate_frame(frame(payload), context())


@pytest.mark.parametrize('raw', [b'', b'\x00'*4, b'\x01\x00\x00\x00{',
    (513).to_bytes(4,'little')+b'x'*513,
    (21).to_bytes(4,'little')+b'{"schema":1,"schema":1}'])
def test_frame_rejects_bad_framing_duplicate_or_oversized_payload(raw):
    with pytest.raises(ValueError): protocol.validate_frame(raw, context())


def test_frame_rejects_trailing_and_truncated_bytes():
    raw = protocol.encode_ping(context())
    for changed in (raw+b'x', raw[:-1]):
        with pytest.raises(ValueError): protocol.validate_frame(changed, context())


def test_duplicate_keys_with_otherwise_valid_context_and_length_are_rejected():
    raw = protocol.encode_ping(context())[4:]
    duplicate = raw[:-1] + b',"schema":1}'
    with pytest.raises(ValueError):
        protocol.validate_frame(len(duplicate).to_bytes(4, 'little')+duplicate, context())


def test_noncanonical_json_cannot_be_an_alternate_fixed_frame():
    value = dict(schema=1, verb='ping', **context())
    raw = json.dumps(value, indent=1).encode('ascii')
    with pytest.raises(ValueError):
        protocol.validate_frame(len(raw).to_bytes(4, 'little')+raw, context())


@pytest.mark.parametrize('change', [lambda c: c.update(parent_pid=True),
    lambda c: c.update(canary='relative'), lambda c: c.update(canary='//server/share/file'),
    lambda c: c.update(canary='C:/synthetic/../foreign'),
    lambda c: c.update(canary='C:/synthetic/file:stream'),
    lambda c: c.update(destination='127.0.0.1'), lambda c: c.update(nonce='x'*32)])
def test_config_rejects_unbounded_or_substituted_fields(change):
    cfg = config(); change(cfg)
    with pytest.raises(ValueError): protocol.validate_config(cfg)


@pytest.mark.parametrize('ok,error', [(True, 5), (False, 0), (False, 6), (0, 5), (False, True)])
def test_only_exact_failed_win32_access_denied_is_observed(ok, error):
    with pytest.raises(ValueError): protocol.denial_fact(ok, error)


def test_actual_denial_fact_and_exact_write_count_are_required():
    assert protocol.denial_fact(False, 5) == {'opened': False, 'winerror': 5, 'status': 'OBSERVED'}
    protocol.require_written(True, 100, 100)
    for values in ((False, 100, 100), (True, 99, 100), (True, True, 1)):
        with pytest.raises(ValueError): protocol.require_written(*values)


def test_closed_environment_and_owned_profile_guard():
    root = 'C:/Users/runner/AppData/Local/Packages/g1-fixture-11111111-1111-4111-8111-111111111111/AC/python-22222222-2222-4222-8222-222222222222'
    protocol.native_scope(root, 'runner', ['--native-child'], 'win32', True)
    protocol.closed_environment({'SystemRoot': 'C:/Windows', 'TEMP': root+'/Data', 'TMP': root+'/Data'})
    for host in ('LS5', 'PC4', 'LS-05'):
        with pytest.raises(ValueError): protocol.native_scope(root, host, ['--native-child'], 'win32', True)
    for environment in ({'PATH': 'x'}, {'SystemRoot':'C:/Windows','GITHUB_TOKEN':'x'}):
        with pytest.raises(ValueError): protocol.closed_environment(environment)


def test_retained_result_writer_is_bounded_and_refuses_repeat(tmp_path):
    (tmp_path/'Data').mkdir(); path=tmp_path/'Data'/'result.json'; path.write_bytes(b'')
    child.write_result(tmp_path, {'status':'PARTIAL_NO_GRID_AUTHORITY'})
    assert json.loads(path.read_bytes()) == {'status':'PARTIAL_NO_GRID_AUTHORITY'}
    with pytest.raises(ValueError): child.write_result(tmp_path, {})


def test_injected_three_denials_and_fixed_frame_produce_no_grid_authority():
    frames = []
    def write(raw): frames.append(raw); return True, len(raw), 0
    result = child.execute_probe(config(), 456, lambda: (False, 5),
                                 lambda: (False, 5), lambda: (False, 5), write)
    assert len(frames) == 1
    assert protocol.validate_frame(frames[0], context())['verb'] == 'ping'
    assert len(result['denials']) == 3
    assert result['status'] == 'PARTIAL_NO_GRID_AUTHORITY'
    assert result['frame_written_bytes'] == len(frames[0])
    assert result['owner_authenticated'] is False and result['process_lifetime_authenticated'] is False
    assert result['execution_authorized'] is False and result['cleanup_authorized'] is False


@pytest.mark.parametrize('fault', [0, 1, 2])
def test_any_unproven_denial_prevents_frame_write(fault):
    calls = []
    operations = [lambda: (False, 5)]*3
    operations[fault] = lambda: (False, 6)
    with pytest.raises(ValueError):
        child.execute_probe(config(), 456, *operations, lambda raw: calls.append(raw))
    assert calls == []


def test_partial_native_write_cannot_produce_completed_result():
    with pytest.raises(ValueError):
        child.execute_probe(config(), 456, lambda: (False, 5), lambda: (False, 5),
                            lambda: (False, 5), lambda raw: (True, len(raw)-1, 0))


def test_self_contained_child_encoder_matches_independent_offline_validator():
    raw = child.encode_ping(context())
    assert protocol.validate_frame(raw, context()) == dict(schema=1, verb='ping', **context())


@pytest.mark.parametrize('module', [protocol, child])
def test_both_config_parsers_reject_duplicates_and_nonfinite(module):
    raw = json.dumps(config()).encode('ascii')
    with pytest.raises(ValueError): module.parse_config(raw[:-1]+b',"schema":1}')
    with pytest.raises(ValueError): module.parse_config(raw.replace(b'123', b'NaN'))


def test_missing_result_slot_is_not_created(tmp_path):
    (tmp_path/'Data').mkdir()
    with pytest.raises(FileNotFoundError): child.write_result(tmp_path, {})
    assert not (tmp_path/'Data'/'result.json').exists()


def test_oversized_result_is_not_written(tmp_path):
    (tmp_path/'Data').mkdir(); path=tmp_path/'Data'/'result.json'; path.write_bytes(b'')
    with pytest.raises(ValueError): child.write_result(tmp_path, {'x':'x'*65536})
    assert path.read_bytes() == b''


def test_denial_failure_carries_only_fixed_code_name_and_raw_numeric_facts():
    with pytest.raises(ValueError) as caught:
        child.execute_probe(config(), 456, lambda: (True, 5), lambda: (False, 5),
                            lambda: (False, 5), lambda raw: (True, len(raw), 0))
    result = child.failure_result('PIPE_READ', caught.value)
    assert result['reason'] == 'DENIAL_NOT_PROVEN_PIPE_READ'
    assert result['opened'] is True and result['winerror'] == 5
    assert result['status'] == 'BLOCKED' and result['cleanup_authorized'] is False


def test_failed_write_carries_fixed_error_without_exception_message():
    with pytest.raises(ValueError) as caught:
        child.execute_probe(config(), 456, lambda: (False, 5), lambda: (False, 5),
                            lambda: (False, 5), lambda raw: (False, 0, 5))
    result = child.failure_result('FRAME_WRITE', caught.value)
    assert result['reason'] == 'FRAME_WRITE_INCOMPLETE' and result['winerror'] == 5
    result = child.failure_result('CONFIG_VALIDATE', ValueError('secret path C:/private token=123'))
    assert result['reason'] == 'VALUE_ERROR'
    assert 'secret' not in json.dumps(result) and 'private' not in json.dumps(result)


def test_guarded_failure_writes_safe_result_only_after_real_scope_allowed(tmp_path):
    (tmp_path/'Data').mkdir(); path=tmp_path/'Data'/'result.json'; path.write_bytes(b'')
    def allowed(state):
        state.update(result_allowed=True, stage='CONFIG_VALIDATE')
        raise ValueError('secret config content')
    assert child.run_guarded(allowed, root=tmp_path) == 1
    result = json.loads(path.read_bytes())
    assert result['stage'] == 'CONFIG_VALIDATE' and result['reason'] == 'VALUE_ERROR'
    assert result['status'] == 'BLOCKED' and result['execution_authorized'] is False
    before=path.read_bytes()
    assert child.run_guarded(allowed, root=tmp_path) == 1
    assert path.read_bytes() == before


def test_scope_failure_writes_nothing_and_missing_slot_is_not_created(tmp_path):
    (tmp_path/'Data').mkdir()
    def unallowed(state): raise ValueError('guard failed')
    assert child.run_guarded(unallowed, root=tmp_path) == 1
    assert not (tmp_path/'Data'/'result.json').exists()
    def allowed(state):
        state.update(result_allowed=True, stage='FRAME_WRITE')
        raise OSError(5, 'private message')
    assert child.run_guarded(allowed, root=tmp_path) == 1
    assert not (tmp_path/'Data'/'result.json').exists()
    path=tmp_path/'Data'/'result.json'; path.write_bytes(b'')
    assert child.run_guarded(unallowed, root=tmp_path) == 1
    assert path.read_bytes() == b''


def test_failure_builder_redacts_unknown_stages_and_noninteger_error_data():
    error = child.ProbeFailure('untrusted message with private path', 'notbool', 'notint')
    result = child.failure_result('C:/private/stage', error)
    assert result['stage'] == 'UNKNOWN_STAGE' and result['reason'] == 'VALUE_ERROR'
    assert result['opened'] is None and result['winerror'] is None
    assert 'private' not in json.dumps(result)
