"""Adversarial fixture-only tests; no native/host/storage effects."""
import copy
import importlib.util
import json
import os
import random
import pytest

if importlib.util.find_spec('cryptography') is None:
    if os.environ.get('GRID_REQUIRE_TEST_ATTESTATION')=='1':raise RuntimeError('MANDATORY_TEST_CRYPTO_MISSING')
    pytest.skip('Optional isolated crypto venv absent',allow_module_level=True)
from installer.tests.vm_test_attestation_fixture import signed,example_plan,NOW
import installer.vm_test_attestation as verifier


def test_challenge_toctou_cannot_consume_an_unverified_nonce(monkeypatch):
    p=example_plan();e,c=signed(p);original=copy.deepcopy(c);state=verifier.TestReplayState()
    inspect=verifier.inspect_evidence
    def mutate(*args):
        report=inspect(*args);c['nonce']='9'*64;c['sequence']=77;return report
    monkeypatch.setattr(verifier,'inspect_evidence',mutate)
    assert verifier.verify_test_fixture(json.dumps(e),p,c,state,NOW)['status']=='BLOCKED'
    assert state._seen=={original['nonce']}
    assert state._sequence=={original['session_id']:original['sequence']}
    monkeypatch.setattr(verifier,'inspect_evidence',inspect)
    with pytest.raises(ValueError,match='VM_TEST_REPLAY'):
        verifier.verify_test_fixture(json.dumps(e),p,original,state,NOW)


def test_plan_input_is_detached_before_inspection(monkeypatch):
    p=example_plan();e,c=signed(p);inspect=verifier.inspect_evidence
    def mutate(raw,passed_plan):
        p['quotas']['cpu']=3
        return inspect(raw,passed_plan)
    monkeypatch.setattr(verifier,'inspect_evidence',mutate)
    assert verifier.verify_test_fixture(json.dumps(e),p,c,verifier.TestReplayState(),NOW)['authentication']=='TEST_KEY_ONLY'


def test_state_method_cannot_be_shadowed_by_caller_attribute():
    state=verifier.TestReplayState()
    with pytest.raises(AttributeError):state.consume=lambda *args:None


def test_backend_exception_is_sanitized_and_does_not_consume(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ed25519
    original=ed25519.Ed25519PublicKey;p=example_plan();e,c=signed(p);state=verifier.TestReplayState()
    class Broken:
        @staticmethod
        def from_public_bytes(_):return Broken()
        def verify(self,*args):raise RuntimeError('PRIVATE_PAYLOAD_BACKEND_TEXT')
    monkeypatch.setattr(ed25519,'Ed25519PublicKey',Broken)
    with pytest.raises(ValueError,match='^VM_TEST_CRYPTO_FAILURE$'):
        verifier.verify_test_fixture(json.dumps(e),p,c,state,NOW)
    monkeypatch.setattr(ed25519,'Ed25519PublicKey',original)
    assert verifier.verify_test_fixture(json.dumps(e),p,c,state,NOW)['status']=='BLOCKED'


def test_bad_second_signer_never_consumes():
    p=example_plan();e,c=signed(p);bad=copy.deepcopy(e);bad['signatures'][1]['signature']='0'*128
    state=verifier.TestReplayState()
    with pytest.raises(ValueError):verifier.verify_test_fixture(json.dumps(bad),p,c,state,NOW)
    assert verifier.verify_test_fixture(json.dumps(e),p,c,state,NOW)['status']=='BLOCKED'


def test_budget_exhaustion_preserves_state():
    p=example_plan();e,c=signed(p);state=verifier.TestReplayState()
    state._seen={f'{i:064x}' for i in range(1024)};before=set(state._seen)
    with pytest.raises(ValueError,match='VM_TEST_REPLAY_BUDGET'):
        verifier.verify_test_fixture(json.dumps(e),p,c,state,NOW)
    assert state._seen==before and not state._sequence


def test_corrupt_state_types_reject_with_fixed_code():
    p=example_plan();e,c=signed(p);state=verifier.TestReplayState();state._sequence=[]
    with pytest.raises(ValueError,match='^VM_TEST_STATE_CORRUPT$'):
        verifier.verify_test_fixture(json.dumps(e),p,c,state,NOW)


def test_seeded_json_mutations_are_fixed_rejections_or_blocked_only():
    from installer.vm_lab_json import canonical,load
    rng=random.Random(6223923239);p=example_plan();e,c=signed(p)
    assert load(canonical(e).decode('ascii'))==json.loads(json.dumps(e))
    for raw in ('['*1000+']'*1000,'x'*65537,'"\\ud800"'):
        state=verifier.TestReplayState()
        with pytest.raises(ValueError):verifier.verify_test_fixture(raw,p,c,state,NOW)
        assert not state._seen
    for _ in range(96):
        value=copy.deepcopy(e)
        field=rng.choice(['schema','domain','canonicalization','payload','signatures'])
        value[field]=rng.choice([None,True,1.0,[],{},'x','😀',1])
        try:r=verifier.verify_test_fixture(json.dumps(value),p,c,verifier.TestReplayState(),NOW)
        except ValueError as exc:assert __import__('re').fullmatch('VM_[A-Z_]{1,64}',str(exc))
        else:assert r['status']=='BLOCKED' and not r['readiness_passed']


def test_no_private_key_api_in_verifier():
    import ast
    from pathlib import Path
    tree=ast.parse(Path(verifier.__file__).read_text(encoding='utf-8-sig'))
    names=[n.id for n in ast.walk(tree) if isinstance(n,ast.Name)]
    imports=[a.name for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom)) for a in n.names]
    assert not any('PrivateKey' in name or name in ('sign','private_bytes') for name in names+imports)
