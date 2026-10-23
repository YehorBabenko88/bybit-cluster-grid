import copy
import hashlib
import json
import pytest
from test_pc4_sid_acl_evidence import fixture, RUN, SIDS
from installer.pc4_security_bundle import verify, cleanup_plan, PROOFS

SHA='a'*40


def bundle():
    raw,_=fixture()
    from installer.pc4_sid_acl_evidence import validate,render_junit
    result=validate(raw,expected_run=RUN,expected_sids=SIDS,expected_sha256=hashlib.sha256(raw.encode()).hexdigest())
    data={'results.jsonl':raw.encode(),'junit.xml':render_junit(result).encode(),
          'manifest.json':json.dumps(dict(run_id=RUN,source_sha=SHA,expected_sids=SIDS,
              execution_authorized=False,readiness_passed=False,airgap_verified=False)).encode(),
          'completed.json':json.dumps(dict(run_id=RUN,reported_cases=10,physical_attestation=False,airgap_verified=False)).encode(),
          'shutdown.json':json.dumps({r:dict(status='EXIT_CONFIRMED',exit_code=0,signal_failed=False) for r in SIDS}).encode()}
    return rehash(data)


def rehash(data):
    data['sha256.json']=json.dumps({n:hashlib.sha256(v).hexdigest() for n,v in data.items() if n!='sha256.json'}).encode()
    return data


def test_synthetic_format_does_not_attest():
    r=verify(bundle(),expected_run=RUN,expected_head=SHA,expected_sids=SIDS)
    assert r['status']=='OFFLINE_FORMAT_PASS' and r['host_verified'] is False
    assert r['physical_attestation'] is False and r['cleanup_authorized'] is False


@pytest.mark.parametrize('fault',['hash','missing','replay','head','sid','fake-pass','duplicate-json',
    'timeout','shutdown-code','physical','path','xml-entity','junit-skip','junit-failure',
    'manifest-physical','manifest-host','manifest-cleanup','bool-exit'])
def test_evidence_tampering_and_faults(fault):
    data=bundle()
    if fault=='hash':data['results.jsonl']+=b' '
    if fault=='missing':del data['shutdown.json']
    if fault in ('replay','head','sid'):
        m=json.loads(data['manifest.json']);m[{'replay':'run_id','head':'source_sha','sid':'expected_sids'}[fault]]='WRONG';data['manifest.json']=json.dumps(m).encode()
    if fault=='fake-pass':data['results.jsonl']=data['results.jsonl'].replace(b'PASS',b'SKIP')
    if fault=='duplicate-json':data['manifest.json']=b'{"run_id":"x","run_id":"y"}'
    if fault=='timeout':data['shutdown.json']=data['shutdown.json'].replace(b'EXIT_CONFIRMED',b'BLOCKED_TIMEOUT')
    if fault=='shutdown-code':data['shutdown.json']=data['shutdown.json'].replace(b'"exit_code": 0',b'"exit_code": 3')
    if fault=='physical':data['completed.json']=data['completed.json'].replace(b'false',b'true')
    if fault.startswith('manifest-'):
        m=json.loads(data['manifest.json']);m[{'manifest-physical':'physical_attestation',
          'manifest-host':'host_verified','manifest-cleanup':'cleanup_authorized'}[fault]]=True
        data['manifest.json']=json.dumps(m).encode()
    if fault=='bool-exit':data['shutdown.json']=data['shutdown.json'].replace(b'"exit_code": 0',b'"exit_code": false')
    if fault=='path':data['../outside']=b'bad'
    if fault=='xml-entity':data['junit.xml']=b'<!DOCTYPE foo [<!ENTITY x "bad">]><foo>&x;</foo>'
    if fault=='junit-skip':data['junit.xml']=data['junit.xml'].replace(b'skipped="0"',b'skipped="1"')
    if fault=='junit-failure':data['junit.xml']=data['junit.xml'].replace(b'<testcase ',b'<testcase injected="true" ',1).replace(b' />',b'><failure /></testcase>',1)
    if fault!='hash':rehash(data) # Hashes alone must not make invalid evidence PASS.
    assert verify(data,expected_run=RUN,expected_head=SHA,expected_sids=SIDS)['status']=='BLOCKED'


@pytest.mark.parametrize('proof',sorted(PROOFS))
@pytest.mark.parametrize('value',[None,False,'true'])
def test_cleanup_fault_injection_never_authorizes(proof,value):
    facts={n:True for n in PROOFS};facts[proof]=value
    r=cleanup_plan(facts)
    assert r['status'] in ('FAIL','BLOCKED') and r['cleanup_authorized'] is False


def test_even_perfect_cleanup_model_stays_blocked():
    assert cleanup_plan({n:True for n in PROOFS})['status']=='BLOCKED'
