"""Untrusted diagnostic JSON never grants execution or physical evidence."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def plan():
    return dict(schema='grid-lsa-readonly-1', mode='PlanOnly', readiness='BLOCKED',
                effective_rights='UNKNOWN', execution_authorized=False,
                physical_tests='0/10 NOT_RUN', records=[], errors=[],
                group_completeness='UNKNOWN', actor_token_observed=False)


def invoke(raw):
    return subprocess.run([sys.executable, '-m', 'installer.lsa_report_contract'],
                          input=raw, capture_output=True, cwd=ROOT)


def blocked(result):
    assert result['status'] == 'BLOCKED'
    assert result['effective_rights'] == 'UNKNOWN'
    assert result['execution_authorized'] is False
    assert result['readiness_passed'] is False
    assert result['physical_attestation'] is False
    assert result['physical_tests'] == '0/10 NOT_RUN'
    assert result['physical_passes'] == 0
    assert result['evidence_class'] == 'UNAUTHENTICATED_DIAGNOSTIC_ONLY'


def test_cli_valid_plan_returns_only_blocked_metadata():
    proc = invoke(json.dumps(plan()).encode())
    assert proc.returncode == 0, proc.stderr.decode(errors='replace')
    result = json.loads(proc.stdout)
    assert result['contract_valid'] is True
    blocked(result)


def review(value):
    from installer.lsa_report_contract import validate
    return validate(json.dumps(value))


def record(principal='GridLabCollector', relation='LOCAL_ACCOUNT'):
    return dict(principal=principal, relation=relation, state='DIRECT_ONLY',
                code='ENUMERATED', ntstatus='0x00000000', win32=0,
                cleanup_failed=False, direct_allow=['SeBatchLogonRight'], direct_deny=[])


def collected():
    data = plan()
    data['mode'] = 'CollectLocalReadOnly'
    data['records'] = [record(), record('GridLabStorage')]
    for alias in ('Everyone', 'AuthenticatedUsers', 'LocalAccount', 'LocalAccountAdmin',
                  'Users', 'Administrators', 'Network', 'Batch', 'Interactive', 'Service',
                  'RemoteInteractive', 'ThisOrganization', 'Local', 'ConsoleLogon'):
        data['records'].append(record(alias, 'CONDITIONAL_CANDIDATE'))
    return data


def test_collected_direct_grants_never_become_effective_or_physical():
    result = review(collected())
    assert result['contract_valid'] is True
    blocked(result)


def test_no_relevant_rights_is_not_no_direct_assignments():
    data = collected()
    data['records'][0]['direct_allow'] = []  # Native result may contain unrelated privileges.
    result = review(data)
    assert result['contract_valid'] is True
    blocked(result)


def test_not_assigned_and_deny_candidates_are_diagnostic_only():
    data = collected()
    data['records'][0].update(code='NO_DIRECT_ASSIGNMENTS', ntstatus='0xC0000034',
                              win32=2, direct_allow=[])
    data['records'][-1]['direct_deny'] = ['SeDenyInteractiveLogonRight']
    result = review(data)
    assert result['contract_valid'] is True
    blocked(result)


@pytest.mark.parametrize('key', list(plan()))
def test_missing_top_level_field_rejected(key):
    data = plan()
    del data[key]
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('key,value', [
    ('schema', 'grid-lsa-readonly-2'), ('mode', 'Execute'), ('mode', 'MOCK'),
    ('readiness', 'PASS'), ('effective_rights', 'ALLOWED'), ('group_completeness', 'COMPLETE'),
    ('execution_authorized', True), ('execution_authorized', 0), ('execution_authorized', None),
    ('execution_authorized', 'false'), ('actor_token_observed', True), ('actor_token_observed', 0),
    ('physical_tests', '10/10 PASS'), ('physical_tests', []), ('errors', None), ('records', {}),
    ('errors', ['LOCAL_IDENTITY_OR_GROUP_ENUMERATION_FAILED']), ('errors', ['untrusted error']),
])
def test_top_level_promotions_and_wrong_types_rejected(key, value):
    data = plan()
    data[key] = value
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('key,value', [
    ('physical_ready', True), ('source', 'MOCK'), ('physical_passes', 10),
    ('status', 'PASS'), ('metadata', {'execution_authorized': True}),
])
def test_unknown_fields_cannot_smuggle_mock_or_physical_pass(key, value):
    data = collected()
    data[key] = value
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('key', list(record()))
def test_missing_record_field_rejected(key):
    data = collected()
    del data['records'][0][key]
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('key,value', [
    ('state', 'PASS'), ('state', 'UNKNOWN'), ('code', 'UNRECOGNIZED'),
    ('code', 'NO_DIRECT_ASSIGNMENTS'), ('code', 'CLEANUP_FAILED'),
    ('ntstatus', '0xC0000022'), ('ntstatus', 0), ('ntstatus', '0x0000000'),
    ('win32', 5), ('win32', False), ('win32', -1), ('win32', 2**32),
    ('cleanup_failed', True), ('cleanup_failed', 0), ('cleanup_failed', None),
    ('direct_allow', ['SeMadeUpRight']), ('direct_allow', ['SeBatchLogonRight'] * 2),
    ('direct_allow', ['SeDenyBatchLogonRight']), ('direct_allow', 'SeBatchLogonRight'),
    ('direct_deny', ['SeBatchLogonRight']), ('direct_deny', None),
    ('relation', 'EFFECTIVE_MEMBER'), ('principal', 'S-1-5-21-1-2-3-1003'),
    ('metadata', {'source': 'MOCK', 'outcome': 'PASS'}),
])
def test_contradictory_records_rejected(key, value):
    data = collected()
    data['records'][0][key] = value
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('code', ['OPEN_FAILED', 'INVALID_HANDLE', 'ENUMERATE_FAILED',
                                 'API_OR_DATA_ERROR', 'CLEANUP_FAILED'])
def test_all_unknown_error_branches_block_consumption(code):
    data = collected()
    data['records'][0].update(state='UNKNOWN', code=code, direct_allow=[],
                              cleanup_failed=(code == 'CLEANUP_FAILED'))
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('change', ['missing_account', 'duplicate_account', 'no_records',
                                  'partial_error', 'plan_records', 'missing_conditional'])
def test_partial_inventory_cannot_be_consumed(change):
    data = collected()
    if change == 'missing_account':
        data['records'].pop(1)
    elif change == 'duplicate_account':
        data['records'][1] = copy.deepcopy(data['records'][0])
    elif change == 'no_records':
        data['records'] = []
    elif change == 'partial_error':
        data['errors'] = ['LOCAL_IDENTITY_OR_GROUP_ENUMERATION_FAILED']
    elif change == 'plan_records':
        data['mode'] = 'PlanOnly'
    else:
        data['records'].pop()
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('raw', [
    '', 'null', '[]', '{', '{"schema":1,"schema":2}',
    json.dumps(plan()).replace('false', 'NaN', 1),
    json.dumps(plan()).replace('false', 'Infinity', 1),
    '[' * 25 + '0' + ']' * 25, ' ' * 65537,
    json.dumps(plan()) + json.dumps(plan()),
    json.dumps(plan()).replace('UNKNOWN', '\\ud800', 1),
], ids=lambda value: 'json-' + str(len(value)))
def test_untrusted_json_parser_fails_closed(raw):
    from installer.lsa_report_contract import validate
    result = validate(raw)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('raw', [b'\xff', b'{', b' ' * 65537], ids=['encoding', 'syntax', 'oversize'])
def test_cli_invalid_input_returns_fixed_blocked_json(raw):
    proc = invoke(raw)
    assert proc.returncode == 2
    assert proc.stderr == b''
    result = json.loads(proc.stdout)
    assert result['contract_valid'] is False
    blocked(result)


def test_unlabelled_mock_cannot_be_authenticated_by_its_shape():
    # Same bytes can be produced by a mock or by a host; neither acquires provenance.
    result = review(collected())
    assert result['contract_valid'] is True
    blocked(result)


def test_direct_local_group_can_replace_one_conditional_alias():
    data = collected()
    data['records'][6] = record('local_group_2', 'DIRECT_LOCAL_GROUP')
    result = review(data)
    assert result['contract_valid'] is True
    blocked(result)


@pytest.mark.parametrize('mutation', ['rights', 'status', 'win32', 'deny'])
def test_no_direct_assignments_requires_consistent_empty_result(mutation):
    data = collected()
    row = data['records'][0]
    row.update(code='NO_DIRECT_ASSIGNMENTS', ntstatus='0xC0000034', win32=2, direct_allow=[])
    if mutation == 'rights':
        row['direct_allow'] = ['SeBatchLogonRight']
    elif mutation == 'status':
        row['ntstatus'] = '0x00000000'
    elif mutation == 'win32':
        row['win32'] = 0
    else:
        row['direct_deny'] = ['SeDenyBatchLogonRight']
    result = review(data)
    assert result['contract_valid'] is False
    blocked(result)


def test_duplicate_json_keys_inside_record_rejected_before_validation():
    from installer.lsa_report_contract import validate
    raw = json.dumps(collected()).replace('"cleanup_failed": false',
        '"cleanup_failed": true, "cleanup_failed": false', 1)
    result = validate(raw)
    assert result['contract_valid'] is False
    blocked(result)


@pytest.mark.parametrize('wrapper', ['json', 'ten_jsonl', 'review_result'])
def test_existing_physical_evidence_parser_rejects_lsa_and_mock_laundering(wrapper):
    import hashlib
    from installer.pc4_sid_acl_evidence import validate
    payload = review(collected()) if wrapper == 'review_result' else collected()
    raw = (json.dumps(payload) + '\n') * (10 if wrapper == 'ten_jsonl' else 1)
    result = validate(raw, expected_run='77777777-7777-4777-8777-777777777777',
        expected_sids={'Collector': 'S-1-5-21-1-2-3-1003', 'Storage': 'S-1-5-21-1-2-3-1004'},
        expected_sha256=hashlib.sha256(raw.encode()).hexdigest())
    assert result['format_valid'] is False and result['reported_passes'] == 0
    assert result['execution_authorized'] is False
    assert result['physical_attestation'] is False


def test_lsa_native_and_physical_package_unchanged_from_223():
    base = 'a2cff9b81bb460a022df785586fc2c300c99590e'
    files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', base,
                                     'lab/lsa-readonly', 'lab/pc4',
                                     'installer/pc4_sid_acl_evidence.py'], cwd=ROOT).decode().splitlines()
    assert len(files) == 12
    for name in files:
        old = subprocess.check_output(['git', 'show', f'{base}:{name}'], cwd=ROOT)
        assert old.replace(b'\r\n', b'\n') == (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
