"""Future offline intent only; no native/SQL/producer/runtime calls."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import pytest
from installer.pgdata_intent_v1 import validate_bundle, validate_text

ROOT = Path(__file__).resolve().parents[1]

def sample():
    return json.loads((ROOT / 'pgdata-intent-v1.example.json').read_text())

def blocked(r):
    assert r['status'] == 'BLOCKED' and r['l1'] == r['l2'] == 'NO-GO'
    assert r['guest_cases'] == '12 NOT_RUN'
    assert all(r[k] is False for k in ('execution_authorized', 'readiness_passed', 'physical_ready', 'schema2_enabled', 'ownership_verified'))

def rebind(m):
    """Attacker can recompute every unsigned digest; structural checks must remain."""
    from installer.vm_lab_json import canonical
    m['intent_sha256'] = hashlib.sha256(canonical(m['intent'])).hexdigest()
    m['journal_sha256'] = hashlib.sha256(m['journal_utf8'].encode()).hexdigest()
    r = json.loads(m['receipt_utf8'])
    r.update(intent_sha256=m['intent_sha256'], journal_sha256=m['journal_sha256'])
    for k in ('run_id', 'node_id', 'root', 'pgdata', 'phase', 'scope'):
        r[k] = m['intent'][k]
    m['receipt_utf8'] = canonical(r).decode() + '\n'
    m['receipt_sha256'] = hashlib.sha256(m['receipt_utf8'].encode()).hexdigest()

def test_valid_metadata_never_authorizes():
    r = validate_bundle(sample()); assert r['metadata_valid']; blocked(r)
    assert r['replay_protection'] == 'CALLER_HISTORY_ONLY_NOT_DURABLE'
    assert 'NATIVE_EVIDENCE_MISSING' in r['blockers']

@pytest.mark.parametrize('path', [
    'L:/GridLab', 'l:\\GridLab', 'L:\\gridlab', 'C:\\GridLab', '\\\\host\\GridLab',
    '\\\\?\\L:\\GridLab', 'L:\\GridLab\\..', 'L:\\GridLab.', 'L:\\GridLab ',
    'L:\\GridLab:ads', 'L:\\GridLab\\', 'L:\\GrіdLab', 'L:\\GridLab\x00'])
def test_bad_parent_even_with_rehashed_receipt(path):
    m = sample(); m['intent']['parent'] = path; rebind(m)
    r = validate_bundle(m); assert not r['metadata_valid']; blocked(r)

@pytest.mark.parametrize('mutation', [
    'old_layout', 'mixed', 'swap_run', 'swap_node', 'lower_node', 'unicode_node',
    'protected_node', 'run_upper', 'run_zero', 'node_reserved', 'traversal',
    'root_alias', 'case_path', 'reparse_claim', 'volume_claim', 'ancestor_claim',
    'token_claim', 'acl_claim', 'native_missing', 'native_true', 'owner_writer',
    'owner_verifier', 'shared_custody', 'same_sid', 'bad_sid', 'missing_observer',
    'stop_writer', 'role_extra', 'scope_live', 'unknown_phase', 'version_two',
    'provenance', 'candidate', 'journal_retired', 'unknown_field'])
def test_structural_attacks_even_after_rehash(mutation):
    m = sample(); i = m['intent']
    if mutation == 'old_layout': i['pgdata'] = i['parent']+'\\'+i['run_id']+'\\'+i['node_id']+'\\pgdata'
    elif mutation == 'mixed': i['pgdata'] = i['root']+'\\pgdata'
    elif mutation == 'swap_run': i['run_id'] = 'b'*32
    elif mutation == 'swap_node': i['node_id'] = 'LAB02'
    elif mutation == 'lower_node': i['node_id'] = 'lab01'
    elif mutation == 'unicode_node': i['node_id'] = 'LАB01'
    elif mutation == 'protected_node': i['node_id'] = 'LS5'
    elif mutation == 'run_upper': i['run_id'] = 'A'*32
    elif mutation == 'run_zero': i['run_id'] = '0'*32
    elif mutation == 'node_reserved': i['node_id'] = 'CON'
    elif mutation == 'traversal': i['pgdata'] += '\\..\\data'
    elif mutation == 'root_alias': i['root'] = i['root'].replace('GridLab', 'GRIDLA~1')
    elif mutation == 'case_path': i['pgdata'] = i['pgdata'].lower()
    elif mutation.endswith('_claim'): i['native'][mutation[:-6]] = 'VERIFIED'
    elif mutation == 'native_missing': del i['native']['volume']
    elif mutation == 'native_true': i['native']['tokens'] = True
    elif mutation == 'owner_writer': i['roles'][2]['principal_id'] = i['roles'][1]['principal_id']
    elif mutation == 'owner_verifier': i['roles'][3]['principal_id'] = i['roles'][1]['principal_id']
    elif mutation == 'shared_custody': i['roles'][4]['custody_domain'] = i['roles'][3]['custody_domain']
    elif mutation == 'same_sid':
        i['roles'][1]['proposed_sid'] = i['roles'][2]['proposed_sid'] = 'S-1-5-21-1-2-3-1001'
    elif mutation == 'bad_sid': i['roles'][1]['proposed_sid'] = 'S-1-5-4294967296'
    elif mutation == 'missing_observer': i['roles'].pop(4)
    elif mutation == 'stop_writer': i['roles'][5]['principal_id'] = i['roles'][2]['principal_id']
    elif mutation == 'role_extra': i['roles'][0]['approved'] = True
    elif mutation == 'scope_live': i['scope'] = 'LIVE_POSTGRESQL'
    elif mutation == 'unknown_phase': i['phase'] = 'ACTIVE'
    elif mutation == 'version_two': i['contract'] = 'SCHEMA2'
    elif mutation == 'provenance': i['root_provenance']['source_commit'] = '0'*40
    elif mutation == 'candidate': i['candidate_sha'] = '0'*40
    elif mutation == 'journal_retired': i['phase'] = 'RETIRED'
    else: i['mapping_override'] = True
    rebind(m); r = validate_bundle(m); assert not r['metadata_valid']; blocked(r)

@pytest.mark.parametrize('flag', ['execution_authorized', 'readiness_passed', 'physical_ready', 'schema2_enabled'])
@pytest.mark.parametrize('value', [True, 0, 1, None, 'false'])
def test_flags_exact_false(flag, value):
    m = sample(); m['intent'][flag] = value; rebind(m)
    r = validate_bundle(m); assert not r['metadata_valid']; blocked(r)

@pytest.mark.parametrize('field', ['producer_plan_utf8', 'journal_utf8', 'receipt_utf8'])
@pytest.mark.parametrize('mutation', ['tamper', 'crlf', 'bom', 'truncate', 'duplicate'])
def test_artifact_bytes(field, mutation):
    m = sample(); raw = m[field]
    if mutation == 'tamper': raw = raw.replace('a'*32, 'b'*32) if 'a'*32 in raw else raw.replace('PREPARED', 'COMMITTED', 1)
    elif mutation == 'crlf': raw = raw.replace('\n', '\r\n') if '\n' in raw else raw+'\r\n'
    elif mutation == 'bom': raw = '\ufeff'+raw
    elif mutation == 'truncate': raw = raw[:-1]
    else: raw = raw.replace('{', '{"schema":1,', 1)
    m[field] = raw; r = validate_bundle(m); assert not r['metadata_valid']; blocked(r)

@pytest.mark.parametrize('field', ['intent_sha256', 'journal_sha256', 'receipt_sha256'])
@pytest.mark.parametrize('value', ['0'*64, 'A'*64, True, None])
def test_digest_mismatch(field, value):
    m = sample(); m[field] = value
    r = validate_bundle(m); assert not r['metadata_valid']; blocked(r)

def test_replayed_id_and_corrupt_history_block():
    m = sample(); rid = json.loads(m['receipt_utf8'])['receipt_id']
    for history in ([rid], [rid, rid], [True], 'not-a-ledger', None):
        r = validate_bundle(m, seen_receipt_ids=history)
        assert not r['metadata_valid']; blocked(r)
    # Empty caller history can be rolled back; must never be called durable protection.
    assert validate_bundle(m, seen_receipt_ids=[])['metadata_valid']
    blocked(validate_bundle(m, seen_receipt_ids=[]))

@pytest.mark.parametrize('raw', ['{}', 'null', '{bad}', '{"a":1,"a":2}', 'NaN', '\ud800', '['*25+'0'+']'*25])
def test_corrupt_outer_json(raw):
    r = validate_text(raw); assert not r['metadata_valid']; blocked(r)

def test_no_io_and_no_input_mutation(monkeypatch):
    m = sample(); saved = copy.deepcopy(m)
    def deny(*a, **k): raise AssertionError('INFRASTRUCTURE_FORBIDDEN')
    monkeypatch.setattr(Path, 'open', deny); monkeypatch.setattr(Path, 'stat', deny)
    monkeypatch.setattr(socket.socket, 'connect', deny); monkeypatch.setattr(subprocess, 'Popen', deny)
    assert validate_bundle(m)['metadata_valid'] and m == saved

@pytest.mark.parametrize('phase,states', [('PREPARED',['PREPARED']), ('COMMITTED',['PREPARED','COMMITTED']), ('RETIRED',['PREPARED','COMMITTED','RETIRED'])])
def test_lifecycle_phase_is_metadata_only(phase, states):
    m = sample(); m['intent']['phase'] = phase
    digest = json.loads(m['producer_plan_utf8'])['plan_sha256']
    m['journal_utf8'] = ''.join('{"schema":1,"plan_sha256":"'+digest+'","state":"'+s+'"}\n' for s in states)
    rebind(m); r = validate_bundle(m); assert r['metadata_valid']; blocked(r)

@pytest.mark.parametrize('mutation', ['status', 'extra', 'id', 'plan_hash', 'writer', 'bool_port'])
def test_forged_receipt_or_plan_with_recomputed_outer_hash(mutation):
    m = sample()
    if mutation in ('status','extra','id','plan_hash'):
        r = json.loads(m['receipt_utf8'])
        if mutation == 'status': r['status'] = 'PASS'
        elif mutation == 'extra': r['approved'] = True
        elif mutation == 'id': r['receipt_id'] = 'not-a-uuid'
        else: r['producer_plan_sha256'] = 'f'*64
        from installer.vm_lab_json import canonical
        m['receipt_utf8'] = canonical(r).decode()+'\n'
        m['receipt_sha256'] = hashlib.sha256(m['receipt_utf8'].encode()).hexdigest()
    else:
        p = json.loads(m['producer_plan_utf8']); p.pop('plan_sha256')
        if mutation == 'writer': p['database_initialization_authorized'] = True
        else: p['postgres_port'] = True
        p['plan_sha256'] = hashlib.sha256(json.dumps(p,separators=(',',':')).encode()).hexdigest()
        m['producer_plan_utf8'] = json.dumps(p,separators=(',',':'))
    r = validate_bundle(m); assert not r['metadata_valid']; blocked(r)

def test_schema1_is_still_separate_and_rejects_powershell_intent():
    from installer.isolated_postgres_plan import validate_postgres_plan, ProvisioningBlocked
    i = sample()['intent']
    p = dict(schema=1, run_id=i['run_id'], node_id=i['node_id'],
             data_root=i['parent']+'\\'+i['run_id']+'\\'+i['node_id']+'\\pgdata',
             port=25432, postgres_major=16, listen_address='127.0.0.1',
             existing_cluster=False, runtime_stopped=True, operator_approved=True)
    r = validate_postgres_plan(p)
    assert r['execution_authorized'] is False and r['physical_ready'] is False
    p['data_root'] = i['pgdata']
    with pytest.raises(ProvisioningBlocked): validate_postgres_plan(p)
    with pytest.raises(ProvisioningBlocked): validate_postgres_plan(i)

def test_same_receipt_id_different_contents_still_replayed():
    from installer.vm_lab_json import canonical
    m = sample(); r = json.loads(m['receipt_utf8']); rid = r['receipt_id']
    m['intent']['roles'][0]['custody_domain'] = 'CHANGED_CUSTODY'
    rebind(m)
    assert validate_bundle(m)['metadata_valid']
    assert not validate_bundle(m, seen_receipt_ids=[rid])['metadata_valid']

def test_empty_history_cannot_establish_continuity_or_atomic_consumption():
    m = sample()
    for _ in range(2):
        r = validate_bundle(m, seen_receipt_ids=[])
        assert r['metadata_valid']; blocked(r)
        assert r['anti_rollback'] == 'NOT_IMPLEMENTED'

def test_all_workflows_keep_new_branch_off_infrastructure():
    import re
    positive = {'protected-staging-offline.yml':'audit/protected-staging-offline-20261022',
                    'pc4-sid-acl-offline.yml': 'audit/codex-pc4-sid-acl-20261021',
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
                assert "github.head_ref != 'planning/pgdata-intent-v1-20261021'" in first
                assert "github.ref_name != 'planning/pgdata-intent-v1-20261021'" in first

def test_exact_inventory_gate_and_safe_workflow():
    text = (ROOT / '.github/workflows/pgdata-intent-offline.yml').read_text()
    assert 'pgdata_intent_offline_inventory.json' in text
    assert 'wasxfail' in text and 'pytest_runtest_logreport' in text
    assert 'git rev-parse HEAD' in text
    assert 'github.event.pull_request.head.sha || github.sha' in text
    assert "('errors','failures','skipped')" in text
