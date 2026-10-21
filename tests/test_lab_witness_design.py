"""Inert trust-boundary contract; no native queries or infrastructure."""
import copy
import json
from pathlib import Path
import socket
import subprocess
import pytest
from installer.lab_witness_design import validate_manifest, validate_text

ROOT = Path(__file__).resolve().parents[1]

def sample():
    return json.loads((ROOT / 'lab-witness.example.json').read_text())

def check_blocked(r):
    assert r['status'] == 'BLOCKED' and r['l1'] == 'NO-GO'
    assert r['physical_deployment'] == 'NO-GO' and r['guest_cases'] == '12 NOT_RUN'
    for k in ('authorized', 'schema2_enabled', 'execution_authorized', 'readiness'):
        assert r[k] is False

def test_example():
    r = validate_manifest(sample())
    assert r['manifest_valid']
    check_blocked(r)
    assert 'CHOICE_REQUIRED' in r['blockers']

@pytest.mark.parametrize('choice', ['A', 'B'])
def test_proposal_never_approves_itself(choice):
    m = sample(); m['choice'] = choice
    r = validate_manifest(m)
    assert r['manifest_valid']; check_blocked(r)
    assert 'TWO_OWNER_REVIEW_REQUIRED' in r['blockers']

@pytest.mark.parametrize('field', ['authorized', 'schema2_enabled', 'execution_authorized', 'readiness'])
@pytest.mark.parametrize('value', [True, 0, 1, None, 'false'])
def test_authority_flags(field, value):
    m = sample(); m[field] = value
    r = validate_manifest(m); assert not r['manifest_valid']; check_blocked(r)

@pytest.mark.parametrize('mutation', [
    'host', 'cidr', 'wildcard', 'endpoint', 'unknown', 'same_owner', 'same_anchor',
    'gateway_owner', 'missing_owner', 'mapping', 'approved', 'time', 'durable',
    'native', 'case_pass', 'case_missing', 'selected_unknown', 'schema_bool',
    'network', 'transfer', 'live_airgap', 'shared_keys', 'rollback', 'base'])
def test_negative_contracts(mutation):
    m = sample()
    if mutation == 'host': m['host'] = 'LS5'
    elif mutation == 'cidr': m['B']['routes'] = ['10.0.0.0/8']
    elif mutation == 'wildcard': m['B']['routes'] = ['*']
    elif mutation == 'endpoint': m['B']['endpoint'] = 'production'
    elif mutation == 'unknown': m['unexpected'] = False
    elif mutation == 'same_owner': m['witnesses'][1]['owner'] = m['witnesses'][0]['owner']
    elif mutation == 'same_anchor': m['witnesses'][1]['anchor_domain'] = m['witnesses'][0]['anchor_domain']
    elif mutation == 'gateway_owner': m['witnesses'][0]['owner'] = 'LAB_OPERATOR'
    elif mutation == 'missing_owner': m['witnesses'][0]['owner'] = None
    elif mutation == 'mapping': m['pgdata_mapping'] = 'COMPATIBLE'
    elif mutation == 'approved': m['reviews'][0] = 'APPROVED'
    elif mutation == 'time': m['trusted_time'] = 'VERIFIED'
    elif mutation == 'durable': m['durable_anchor'] = 'IMPLEMENTED'
    elif mutation == 'native': m['native_evidence'] = 'PASS'
    elif mutation == 'case_pass': m['cases'][0] = 'PASS'
    elif mutation == 'case_missing': m['cases'].pop()
    elif mutation == 'selected_unknown': m['choice'] = 'AUTO'
    elif mutation == 'schema_bool': m['schema'] = True
    elif mutation == 'network': m['B']['enabled'] = True
    elif mutation == 'transfer': m['A']['transfer_enabled'] = True
    elif mutation == 'live_airgap': m['A']['live_freshness'] = 'VERIFIED'
    elif mutation == 'shared_keys': m['witnesses'][1]['key_custody'] = m['witnesses'][0]['key_custody']
    elif mutation == 'rollback': m['correlated_rollback'] = 'PREVENTED'
    else: m['planning_base'] = '0' * 40
    r = validate_manifest(m); assert not r['manifest_valid']; check_blocked(r)

@pytest.mark.parametrize('raw', ['{}', 'null', '[]', '{"a":1,"a":2}', 'NaN', '\ud800', '[' * 25 + '0' + ']' * 25])
def test_invalid_json(raw):
    r = validate_text(raw); assert not r['manifest_valid']; check_blocked(r)

def test_no_side_effects(monkeypatch):
    m = sample(); before = copy.deepcopy(m)
    def deny(*a, **k): raise AssertionError('INFRASTRUCTURE_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(subprocess, 'Popen', deny)
    monkeypatch.setattr(Path, 'open', deny)
    monkeypatch.setattr(Path, 'stat', deny)
    assert validate_manifest(m)['manifest_valid']
    assert m == before

def test_all_workflows_exclude_unapproved_infrastructure():
    import re
    positive = {'lab-airgap-a.yml': 'planning/lab-airgap-a-20261021',
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
                assert "github.head_ref != 'planning/lab-witness-l1-20261020'" in first
                assert "github.ref_name != 'planning/lab-witness-l1-20261020'" in first

def test_junit_gate_checks_exact_sha_and_no_false_pass():
    text = (ROOT / '.github/workflows/lab-witness-l1.yml').read_text()
    assert 'github.event.pull_request.head.sha || github.sha' in text
    assert 'git rev-parse HEAD' in text
    assert "('errors','failures','skipped')" in text
    assert text.count('==164') == 2
    assert 'tests/test_lab_witness_design.py' in text
