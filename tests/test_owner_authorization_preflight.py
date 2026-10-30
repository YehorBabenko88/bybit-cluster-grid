"""Pure metadata preparation tests; never host authorization or recovery."""
import copy
import json

import pytest
from integration.owner_authorization_preflight import assess_preparation as assess


def proposal():
    scope = dict(head_sha='a'*40, artifact_sha256='b'*64, owner_key_sha256='c'*64,
                 host_id='11111111-1111-4111-8111-111111111111',
                 session_id='22222222-2222-4222-8222-222222222222',
                 boot_id='33333333-3333-4333-8333-333333333333', action='cleanup')
    return dict(schema=1, scope=scope, recovery=dict(previous_boot_id=scope['boot_id'],
                current_boot_id=scope['boot_id'], handles_lost=False,
                journal_sha256=None, anchor_sha256=None))


def evaluate(value):
    return assess(json.dumps(value), copy.deepcopy(value['scope']))


def test_matching_metadata_and_same_boot_never_grant_owner_or_cleanup_authority():
    result = evaluate(proposal())
    assert result['metadata_matches'] is True
    assert result['status'] == 'BLOCKED'
    assert result['authentication'] == 'NOT_IMPLEMENTED'
    for field in ('execution_authorized', 'cleanup_authorized', 'readiness_passed', 'automatic_resume'):
        assert result[field] is False
    assert result['durable_replay'] == 'NOT_IMPLEMENTED'


@pytest.mark.parametrize('field,value', [
    ('head_sha', 'd'*40), ('artifact_sha256', 'd'*64), ('owner_key_sha256', 'd'*64),
    ('host_id', '99999999-9999-4999-8999-999999999999'),
    ('session_id', '99999999-9999-4999-8999-999999999999'),
    ('boot_id', '99999999-9999-4999-8999-999999999999'), ('action', 'execute')])
def test_scope_substitution_does_not_match_expected_metadata(field, value):
    data = proposal(); expected = copy.deepcopy(data['scope']); data['scope'][field] = value
    result = assess(json.dumps(data), expected)
    assert result['metadata_matches'] is False
    assert result['status'] == 'BLOCKED'
    assert 'SCOPE_MISMATCH' in result['blockers']


@pytest.mark.parametrize('changed_boot,lost_handles', [(True, False), (False, True), (True, True)])
def test_reboot_or_handle_loss_requires_retention_and_fresh_authorization(changed_boot, lost_handles):
    data = proposal(); data['recovery']['handles_lost'] = lost_handles
    if changed_boot:
        data['recovery']['previous_boot_id'] = '99999999-9999-4999-8999-999999999999'
    result = evaluate(data)
    assert result['recovery_disposition'] == 'RETAIN_FOR_REVIEW'
    assert 'FRESH_OWNER_AUTHORIZATION_REQUIRED' in result['blockers']
    assert 'HANDLE_REACQUISITION_UNIMPLEMENTED' in result['blockers']
    assert result['cleanup_authorized'] is False


def test_supplied_hashes_do_not_establish_nonrollback_anchor_or_trusted_journal():
    data = proposal(); data['recovery'].update(journal_sha256='d'*64, anchor_sha256='d'*64)
    result = evaluate(data)
    assert 'EXTERNAL_NONROLLBACK_ANCHOR_UNIMPLEMENTED' in result['blockers']
    assert 'DURABLE_REPLAY_LEDGER_UNIMPLEMENTED' in result['blockers']
    assert result['execution_authorized'] is False


@pytest.mark.parametrize('mutate', [
    lambda x: x.update(schema=True),
    lambda x: x.update(execution_authorized=True),
    lambda x: x['scope'].update(action='delete-recursive'),
    lambda x: x['scope'].update(owner_key_sha256='not-a-key'),
    lambda x: x['scope'].update(host_id='not-a-uuid'),
    lambda x: x['recovery'].update(handles_lost=0),
    lambda x: x['recovery'].update(anchor_sha256='short'),
    lambda x: x['recovery'].update(current_boot_id='99999999-9999-4999-8999-999999999999'),
])
def test_invalid_or_promoted_input_fails_closed(mutate):
    data = proposal(); mutate(data)
    result = evaluate(data)
    assert result['metadata_matches'] is False
    assert 'INVALID_PREPARATION_INPUT' in result['blockers']
    assert result['cleanup_authorized'] is False


@pytest.mark.parametrize('raw', ['{"schema":1,"schema":1}', '['*30+']'*30, 'x'*65537],
                         ids=['duplicate', 'deep', 'oversized'])
def test_bounded_loader_rejects_duplicate_deep_and_oversized_input(raw):
    result = assess(raw, proposal()['scope'])
    assert 'INVALID_PREPARATION_INPUT' in result['blockers']


def test_caller_context_is_not_mutated_and_repeated_calls_cannot_consume_or_authorize():
    data = proposal(); expected = copy.deepcopy(data['scope']); before = copy.deepcopy(expected)
    first = assess(json.dumps(data), expected); second = assess(json.dumps(data), expected)
    assert expected == before
    assert first == second
    assert first['execution_authorized'] is False


def test_offline_metadata_never_promotes_physical_host_or_safety_evidence():
    result = evaluate(proposal())
    assert result['physical_ready'] is False
    assert result['host_verified'] is False
    assert result['verified_safety_cases'] == 0
