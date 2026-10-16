"""Offline TEST-KEY-ONLY verifier. Never a real attestor or authorization capability."""
from datetime import datetime, timezone
import json
import re
import threading
from types import MappingProxyType
from installer.vm_lab_json import canonical,load,check_value
from installer.vm_lab_plan import _shape,_need,_guid,_digest
from installer.vm_lab_evidence import inspect_evidence

DOMAIN='GRID_VM_LAB_TEST_ATTESTATION_V1'
CANON='GRID_JSON_INTEGER_V1'
# PUBLIC synthetic fixture roots, not machine/organization/production trust roots.
_ROOTS=MappingProxyType({
 'test-observer-v1':('observer','55555555-5555-4555-8555-555555555555','03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8'),
 'test-approval-v1':('approval','66666666-6666-4666-8666-666666666666','29acbae141bccaf0b22e1a94d34d0bc7361e526d0bfe12c89794bc9322966dd7'),
})


class TestReplayState:
    """Bounded process-local test ledger; reset/restart is NOT replay protection."""
    __test__=False
    def __init__(self):self._lock=threading.Lock();self._seen=set();self._sequence={}
    def consume(self,session,nonce,sequence):
        with self._lock:
            _need(nonce not in self._seen and sequence>self._sequence.get(session,0),'VM_TEST_REPLAY')
            _need(len(self._seen)<1024,'VM_TEST_REPLAY_BUDGET')
            self._seen.add(nonce);self._sequence[session]=sequence


def _integer_json(value):
    check_value(value);stack=[value]
    while stack:
        item=stack.pop()
        _need(type(item) is not float,'VM_TEST_CANONICAL_NUMBER')
        if type(item) is dict:stack.extend(item.values())
        elif type(item) is list:stack.extend(item)


def _time(value):
    _need(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',value),'VM_TEST_TIME_INVALID')
    try:return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:raise ValueError('VM_TEST_TIME_INVALID') from None


def _challenge(c):
    check_value(c);_integer_json(c)
    _shape(c,'session_id nonce sequence code_sha256 artifact_sha256')
    _guid(c['session_id']);_digest(c['nonce']);_digest(c['code_sha256']);_digest(c['artifact_sha256'])
    _need(type(c['sequence']) is int and 1<=c['sequence']<2**63,'VM_TEST_SEQUENCE_INVALID')


def verify_test_fixture(raw,plan,challenge,state,now):
    """Trusted caller supplies TEST challenge/state/time. No wall clock or I/O used."""
    _need(type(state) is TestReplayState,'VM_TEST_STATE_REQUIRED')
    _challenge(challenge)
    envelope=load(raw);_integer_json(envelope)
    _shape(envelope,'schema domain canonicalization payload signatures')
    _need(type(envelope['schema']) is int and envelope['schema']==1 and
          envelope['domain']==DOMAIN and envelope['canonicalization']==CANON,'VM_TEST_PROTOCOL_INVALID')
    payload=envelope['payload'];_shape(payload,'draft challenge observer_id approval_id issued_at expires_at')
    _challenge(payload['challenge'])
    _need(canonical(payload['challenge'])==canonical(challenge),'VM_TEST_CHALLENGE_MISMATCH')
    _need(payload['observer_id']==_ROOTS['test-observer-v1'][1] and
          payload['approval_id']==_ROOTS['test-approval-v1'][1],'VM_TEST_IDENTITY_UNTRUSTED')
    issued,expires,current=_time(payload['issued_at']),_time(payload['expires_at']),_time(now)
    _need(issued<=current<expires and 0<(expires-issued).total_seconds()<=300,'VM_TEST_FRESHNESS')
    report=inspect_evidence(json.dumps(payload['draft']),plan)
    _need(payload['draft']['payload']['observer']['id']==payload['observer_id'],'VM_TEST_OBSERVER_MISMATCH')
    signatures=envelope['signatures']
    _need(type(signatures) is list and len(signatures)==2,'VM_TEST_SIGNATURES_REQUIRED')
    try:
        import cryptography
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature,UnsupportedAlgorithm
    except ImportError:raise ValueError('VM_TEST_CRYPTO_UNAVAILABLE') from None
    _need(cryptography.__version__=='50.0.2','VM_TEST_CRYPTO_VERSION')
    for signature,key_id in zip(signatures,('test-observer-v1','test-approval-v1')):
        _shape(signature,'key_id role algorithm signature')
        role,_,key_hex=_ROOTS[key_id]
        _need(signature['key_id']==key_id and signature['role']==role and
              signature['algorithm']=='Ed25519','VM_TEST_KEY_OR_ALGORITHM')
        _need(type(signature['signature']) is str and re.fullmatch('[0-9a-f]{128}',signature['signature']),'VM_TEST_SIGNATURE_FORMAT')
        header={k:signature[k] for k in ('key_id','role','algorithm')}
        body={k:envelope[k] for k in ('schema','domain','canonicalization')}
        body.update(payload=payload,signer=header)
        message=DOMAIN.encode('ascii')+b'\x00'+canonical(body)
        try:Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(bytes.fromhex(signature['signature']),message)
        except (InvalidSignature,UnsupportedAlgorithm,ValueError):raise ValueError('VM_TEST_SIGNATURE_INVALID') from None
    # Consume only after BOTH signatures and all semantic constraints pass.
    state.consume(challenge['session_id'],challenge['nonce'],challenge['sequence'])
    report.update(authentication='TEST_KEY_ONLY',signature_result='VERIFIED_PUBLIC_TEST_FIXTURE')
    report['blockers']+=['PUBLIC_TEST_KEYS_NOT_AUTHORITY','NO_DURABLE_REPLAY_OR_TRUSTED_CLOCK',
                         'NO_REAL_OBSERVER_OR_APPROVAL_ATTESTATION']
    return report
