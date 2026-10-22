"""Offline proposal tests, not evidence of any physical safety property."""
import copy
import json
from pathlib import Path
import socket
import subprocess
import pytest
from installer.lab_airgap_a import validate_manifest, validate_text

ROOT = Path(__file__).resolve().parents[1]

def sample():
    return json.loads((ROOT / 'lab-airgap-a.example.json').read_text())

def blocked(result):
    assert result['status'] == 'BLOCKED'
    assert result['l1'] == result['l2'] == 'NO-GO'
    assert result['guest_cases'] == '12 NOT_RUN'
    for key in ('authorized', 'execution_authorized', 'readiness', 'physical_ready', 'schema2_enabled'):
        assert result[key] is False

def test_proposal_valid_but_not_approved():
    result = validate_manifest(sample())
    assert result['manifest_valid']; blocked(result)
    assert 'TWO_INDEPENDENT_HUMAN_REVIEWS_REQUIRED' in result['blockers']

@pytest.mark.parametrize('key', ['authorized', 'execution_authorized', 'readiness', 'physical_ready', 'schema2_enabled'])
@pytest.mark.parametrize('value', [True, 0, 1, None, 'false'])
def test_no_authority_promotion(key, value):
    m = sample(); m[key] = value
    r = validate_manifest(m); assert not r['manifest_valid']; blocked(r)

@pytest.mark.parametrize('field', ['wifi', 'bluetooth', 'routing', 'nat', 'bridged_nic', 'tailscale', 'production', 'internet', 'shared_clipboard', 'shared_folders', 'host_mounts'])
def test_forbidden_boundary(field):
    m = sample(); m['topology'][field] = True
    r = validate_manifest(m); assert not r['manifest_valid']; blocked(r)

@pytest.mark.parametrize('mutation', [
    'B', 'both', 'auto', 'approval', 'missing_second', 'ai_review', 'duplicate_observer',
    'operator_observer', 'stop_operator', 'host', 'cidr', 'route', 'gateway', 'native_pass',
    'case_pass', 'case_missing', 'case_duplicate', 'case_unknown', 'anchor', 'time',
    'freshness', 'transfer_inbound', 'autorun', 'custody', 'digest_proof', 'executed',
    'pgdata', 'epoch', 'base', 'schema_bool', 'unknown', 'review_verified'])
def test_negative_contracts(mutation):
    m = sample()
    if mutation in ('B', 'both', 'auto'): m['variant'] = mutation
    elif mutation == 'approval': m['owner_direction'] = 'APPROVED'
    elif mutation == 'missing_second': m['reviews'].pop()
    elif mutation == 'ai_review': m['reviews'][1]['reviewer'] = 'AI'
    elif mutation == 'duplicate_observer': m['roles'][2]['custody'] = m['roles'][1]['custody']
    elif mutation == 'operator_observer': m['roles'][1]['custody'] = m['roles'][0]['custody']
    elif mutation == 'stop_operator': m['roles'][3]['custody'] = m['roles'][0]['custody']
    elif mutation == 'host': m['host'] = 'LS7'
    elif mutation == 'cidr': m['topology']['cidr'] = '10.0.0.0/8'
    elif mutation == 'route': m['topology']['routes'] = ['*']
    elif mutation == 'gateway': m['topology']['gateway'] = 'witness'
    elif mutation == 'native_pass': m['native_evidence'] = 'PASS'
    elif mutation == 'case_pass': m['cases'][0]['execution'] = 'PASS'
    elif mutation == 'case_missing': m['cases'].pop()
    elif mutation == 'case_duplicate': m['cases'][1] = m['cases'][0]
    elif mutation == 'case_unknown': m['cases'][0]['case'] = 'fake'
    elif mutation == 'anchor': m['anti_rollback'] = 'IMPLEMENTED'
    elif mutation == 'time': m['trusted_time'] = 'VERIFIED'
    elif mutation == 'freshness': m['transfer']['freshness'] = 'LIVE'
    elif mutation == 'transfer_inbound': m['transfer']['inbound_receipts'] = True
    elif mutation == 'autorun': m['transfer']['autorun'] = True
    elif mutation == 'custody': m['transfer']['custody'] = 'VERIFIED'
    elif mutation == 'digest_proof': m['transfer']['hash_proves_freshness'] = True
    elif mutation == 'executed': m['execution'] = 'COMPLETE'
    elif mutation == 'pgdata': m['pgdata_mapping'] = 'COMPATIBLE'
    elif mutation == 'epoch': m['epoch_continuity'] = 'VERIFIED'
    elif mutation == 'base': m['planning_base'] = '0' * 40
    elif mutation == 'schema_bool': m['schema'] = True
    elif mutation == 'review_verified': m['reviews'][0]['decision'] = 'APPROVED'
    else: m['command'] = 'initdb'
    r = validate_manifest(m); assert not r['manifest_valid']; blocked(r)

@pytest.mark.parametrize('raw', ['{}', '[]', 'null', '{bad}', '{"a":1,"a":2}', 'NaN', '\ud800', '['*25+'0'+']'*25, 'x'*65537], ids=['empty','list','null','broken','duplicate','nonfinite','surrogate','deep','oversized'])
def test_bad_json_fixed_diagnostic(raw):
    r = validate_text(raw); assert not r['manifest_valid']; blocked(r)
    assert 'raw' not in r and r['errors'] == ['AIRGAP_CONTRACT_INVALID']

def test_pure_and_non_mutating(monkeypatch):
    m = sample(); saved = copy.deepcopy(m)
    def deny(*args, **kwargs): raise AssertionError('INFRASTRUCTURE_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(subprocess, 'Popen', deny)
    monkeypatch.setattr(Path, 'open', deny)
    monkeypatch.setattr(Path, 'stat', deny)
    assert validate_manifest(m)['manifest_valid']
    assert m == saved

def test_evidence_template_never_accepted_as_receipt_or_manifest():
    m = json.loads((ROOT / 'docs/lab-airgap-a/evidence-template.json').read_text())
    assert m['kind'] == 'DESIGN_TEMPLATE_NOT_EVIDENCE'
    assert m['execution'] == 'NOT_RUN' and m['status'] == 'UNVERIFIED'
    assert all(m[k] is False for k in ('authorized', 'execution_authorized', 'readiness', 'physical_ready', 'schema2_enabled'))
    assert all(m[k] is None for k in ('candidate_sha', 'run_id', 'case', 'attempt_id', 'sequence', 'actual_result_reference'))
    assert m['artifacts'] == [] and m['custody_handoffs'] == []
    assert all(r['decision'] == 'NOT_REVIEWED' for r in m['human_reviews'])
    r = validate_manifest(m); assert not r['manifest_valid']; blocked(r)

def test_inherited_jobs_excluded_and_new_workflow_pure():
    import re
    positive = {'pc4-sid-acl-offline.yml': 'audit/codex-pc4-sid-acl-20261021',
                'protected-staging-offline.yml': 'audit/protected-staging-offline-20261022',
                'pgdata-intent-offline.yml': 'planning/pgdata-intent-v1-20261021',
                'lab-airgap-a.yml': 'planning/lab-airgap-a-20261021',
                'lab-witness-l1.yml': 'planning/lab-witness-l1-20261020',
                'windows-lab-planning.yml': 'planning/windows-lab-l0-20261020',
                'offline-rc-review.yml': 'review/offline-rc-20261020'}
    for p in (ROOT / '.github/workflows').glob('*.yml'):
        text = p.read_text()
        for job in re.split(r'(?m)^  [A-Za-z0-9_-]+:\n', text.split('jobs:\n', 1)[1])[1:]:
            first = job.splitlines()[0]
            if p.name in positive:
                branch = positive[p.name]
                assert "github.head_ref == '" + branch + "'" in first
                assert "github.ref_name == '" + branch + "'" in first
                assert 'services:' not in text and 'self-hosted' not in text
            else:
                assert "github.head_ref != 'planning/lab-airgap-a-20261021'" in first
                assert "github.ref_name != 'planning/lab-airgap-a-20261021'" in first

def test_ci_exact_scope_and_zero_skip_gate():
    text = (ROOT / '.github/workflows/lab-airgap-a.yml').read_text()
    assert text.count('==246') == 2
    assert 'tests/test_lab_airgap_a.py' in text
    assert 'git rev-parse HEAD' in text
    assert 'github.event.pull_request.head.sha || github.sha' in text
    assert "('errors','failures','skipped')" in text
