"""Synthetic crypto proof only: public test seeds and NO real observer."""
import copy
import importlib.util
import json
import os
import pytest

if importlib.util.find_spec('cryptography') is None:
    if os.environ.get('GRID_REQUIRE_TEST_ATTESTATION')=='1':raise RuntimeError('MANDATORY_TEST_CRYPTO_MISSING')
    pytest.skip('Optional test-key-only crypto venv absent; no authenticated observation',allow_module_level=True)

from installer.tests.vm_test_attestation_fixture import signed,example_plan,NOW,SEEDS


def verify(e,p,c,state=None,now=NOW):
    from installer.vm_test_attestation import verify_test_fixture,TestReplayState
    return verify_test_fixture(json.dumps(e),p,c,state if state is not None else TestReplayState(),now)


def test_valid_double_signature_is_test_key_only_and_permanently_blocked():
    p=example_plan();e,c=signed(p);r=verify(e,p,c)
    assert r['authentication']=='TEST_KEY_ONLY' and r['status']=='BLOCKED'
    assert not r['readiness_passed'] and not r['physical_ready'] and not r['execution_authorized']
    assert r['verified_safety_cases']==0 and len(r['negative_cases'])==12
    assert all(x['execution']=='NOT_RUN' for x in r['negative_cases'])


@pytest.mark.parametrize('mutation',['key','algorithm','unsigned','role','public_key','version','canonical',
 'observer','vm','host','image','token','pass','reorder','missing','plan','nonce','sequence','code','artifact',
 'expired','future','ttl','timestamp','approval','revoked','signature','float','session'])
def test_forged_even_resigned_fixtures_rejected(mutation):
    from installer.vm_lab_evidence import digest
    p=example_plan();e,c=signed(p);payload=e['payload']
    if mutation in ('vm','host','image','token','pass','reorder','missing'):
        d=payload['draft']['payload']
        if mutation=='vm':d['vm_id']='99999999-9999-4999-8999-999999999999'
        elif mutation=='host':d['host_id']='LAB-HOST-99999999-9999-4999-8999-999999999999'
        elif mutation=='image':d['image_sha256']='f'*64
        elif mutation=='token':d['identity_evidence']='ATTESTED'
        elif mutation=='pass':d['negative_cases'][0]['execution']='PASS'
        elif mutation=='reorder':d['negative_cases'].reverse()
        else:d['negative_cases'].pop()
        payload['draft']['payload_sha256']=digest(d)
    elif mutation=='observer':payload['observer_id']='99999999-9999-4999-8999-999999999999'
    elif mutation=='approval':payload['approval_id']=payload['observer_id']
    elif mutation=='plan':payload['draft']['plan_sha256']='f'*64
    elif mutation=='nonce':payload['challenge']['nonce']='f'*64
    elif mutation=='sequence':payload['challenge']['sequence']=2
    elif mutation=='session':payload['challenge']['session_id']='99999999-9999-4999-8999-999999999999'
    elif mutation=='code':payload['challenge']['code_sha256']='f'*64
    elif mutation=='artifact':payload['challenge']['artifact_sha256']='f'*64
    elif mutation=='expired':payload['expires_at']='2026-10-16T20:00:05Z'
    elif mutation=='future':payload['issued_at']='2026-10-16T20:00:20Z'
    elif mutation=='ttl':payload['expires_at']='2026-10-17T20:00:00Z'
    elif mutation=='timestamp':payload['issued_at']='2026-10-16T20:00:00+00:00'
    elif mutation=='float':payload['challenge']['sequence']=1.0
    e,_=signed(p,payload)  # Even valid test signatures must not authorize false claims.
    if mutation=='key':e['signatures'][0]['key_id']='unknown'
    elif mutation=='algorithm':e['signatures'][0]['algorithm']='HS256'
    elif mutation=='unsigned':e['signatures'].pop()
    elif mutation=='role':e['signatures'][0]['role']='approval'
    elif mutation=='public_key':e['signatures'][0]['public_key']='f'*64
    elif mutation=='version':e['schema']=True
    elif mutation=='canonical':e['canonicalization']='JCS'
    elif mutation=='revoked':e['signatures'][0]['key_id']='test-observer-v0-revoked'
    elif mutation=='signature':e['signatures'][0]['signature']='0'*128
    with pytest.raises(ValueError):verify(e,p,c)


def test_key_substitution_and_tampering_without_resigning_rejected():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    p=example_plan();e,c=signed(p)
    e['payload']['expires_at']='2026-10-16T20:03:00Z'
    with pytest.raises(ValueError):verify(e,p,c)
    e,c=signed(p)
    from installer.vm_lab_json import canonical
    from installer.tests.vm_test_attestation_fixture import DOMAIN
    header={k:e['signatures'][0][k] for k in ('key_id','role','algorithm')}
    body={k:e[k] for k in ('schema','domain','canonicalization')}
    body.update(payload=e['payload'],signer=header)
    message=DOMAIN.encode()+b'\x00'+canonical(body)
    e['signatures'][0]['signature']=Ed25519PrivateKey.from_private_bytes(bytes([99])*32).sign(message).hex()
    with pytest.raises(ValueError):verify(e,p,c)


def test_replay_consumed_only_after_verification_and_monotonic_in_one_state():
    from installer.vm_test_attestation import TestReplayState
    p=example_plan();e,c=signed(p);state=TestReplayState();bad=copy.deepcopy(e)
    bad['signatures'][0]['signature']='0'*128
    with pytest.raises(ValueError):verify(bad,p,c,state)
    assert verify(e,p,c,state)['status']=='BLOCKED'
    with pytest.raises(ValueError):verify(e,p,c,state)
    payload=copy.deepcopy(e['payload']);payload['challenge']['nonce']='9'*64
    next_e,next_c=signed(p,payload);next_c=payload['challenge']
    with pytest.raises(ValueError):verify(next_e,p,next_c,state)
    payload['challenge']['sequence']=2
    next_e,_=signed(p,payload)
    assert verify(next_e,p,payload['challenge'],state)['status']=='BLOCKED'
    payload['challenge']['session_id']='99999999-9999-4999-8999-999999999999'
    payload['challenge']['sequence']=1
    next_e,_=signed(p,payload)
    with pytest.raises(ValueError):verify(next_e,p,payload['challenge'],state)


def test_concurrent_replay_has_one_test_acceptance():
    from concurrent.futures import ThreadPoolExecutor
    from installer.vm_test_attestation import TestReplayState
    p=example_plan();e,c=signed(p);state=TestReplayState()
    def attempt(_):
        try:verify(e,p,c,state);return 1
        except ValueError:return 0
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(attempt,range(4)))==1


def test_duplicate_json_and_unknown_fields_fail_closed():
    from installer.vm_test_attestation import verify_test_fixture,TestReplayState
    p=example_plan();e,c=signed(p)
    raw=json.dumps(e).replace('"schema": 1','"schema": 1, "schema": 1',1)
    with pytest.raises(ValueError):verify_test_fixture(raw,p,c,TestReplayState(),NOW)
    e['readiness_passed']=True
    with pytest.raises(ValueError):verify(e,p,c)
