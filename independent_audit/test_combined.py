"""Offline RC regressions, including all ten former P2 reproductions; no xfail."""
import base64, dataclasses, importlib.util, json, pathlib, socket, subprocess, sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
COMBINED=ROOT
sys.path.insert(0,str(COMBINED))
from installer.pgdata_cross_contract import inspect_producer_journal_format,check_pgdata_contract
from audit.integration_ci.pg_journal_reader import inspect_journal_bytes
from audit.integration_ci.pg_pytest_receipt import validate_receipt
from vm_principal_lab.evidence_binding import audit_evidence_binding
from vm_principal_lab.cross_guest_isolation import audit_cross_guest_isolation
from vm_principal_lab.offline_principals import PrincipalEvidence
from installer.contract_boundary_audit import audit_contracts,ContractBoundaryBlocked
from installer.vm_replay_model import ReplayModel
from vm_principal_lab.evidence_consistency import EvidenceClaim,detect_evidence_conflicts

def helper(name):
    s=importlib.util.spec_from_file_location('helper_'+name,COMBINED/'tests'/name)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
B=helper('test_contract_boundary_audit.py')
E=helper('test_vm_principal_evidence_binding.py')
P=helper('test_pgdata_cross_contract.py')

@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('AUDIT_EXTERNAL_EFFECT_FORBIDDEN')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)

def journal(d='a'*64,state='PREPARED'):
    return json.dumps(dict(schema=1,plan_sha256=d,state=state),separators=(',',':'),ensure_ascii=False)+'\n'

@pytest.mark.parametrize('bad',[
    '{"schema":2,"schema":1,"plan_sha256":"'+'a'*64+'","state":"PREPARED"}\n',
    journal().replace(':',': '),journal().replace('\n','\r\n'),'\ud800\n','{"bad":1}\n',journal()[:-1]])
def test_previous_reader_findings_fixed(bad):
    r=inspect_journal_bytes(bad,'a'*64)
    assert not r['metadata_valid'] and not r['execution_authorized']

def test_reader_wrong_unicode_digest_returns_blocked():
    assert not inspect_journal_bytes(journal('é'*64),'a'*64)['metadata_valid']

@pytest.mark.parametrize('bad',['[1,2,3]\n','[[],[],[]]\n'])
def test_pg_array_journal_returns_blocker(bad):
    assert inspect_producer_journal_format(bad).startswith('JOURNAL_')

def xml(scope='tests.test_pgdata_cross_contract',count=23):
    return '<testsuite>'+''.join(f'<testcase classname="{scope}" name="invented_{i}"/>' for i in range(count))+'</testsuite>'

@pytest.mark.parametrize('scope',['tests.test_pgdata_cross_contract','evil.test_pgdata_cross_contract_not_real'])
def test_junit_fake_nodeids_cannot_prove_coverage(scope):
    assert validate_receipt(xml(scope),'a'*40,'a'*40,['tests/test_pgdata_cross_contract.py::'+n for n in vars(P) if n.startswith('test_')])

def test_real_current_pg_test_count_exceeds_minimum():
    assert len([n for n in vars(P) if n.startswith('test_')])==28

def test_receipt_requires_current_complete_collected_set():
    names=[n for n in vars(P) if n.startswith('test_')][:23]
    report='<testsuite>'+''.join(f'<testcase classname="tests.test_pgdata_cross_contract" name="{n}"/>' for n in names)+'</testsuite>'
    assert validate_receipt(report,'a'*40,'a'*40,['tests/test_pgdata_cross_contract.py::'+n for n in vars(P) if n.startswith('test_')])

def test_sid_overflow_rejected():
    sid='S-1-5-4294967296'
    r=audit_evidence_binding(E.evidence(declared_sid=sid,actual_sid=sid,token_user_sid=sid,object_owner_sid=sid))
    assert any('INVALID_SID' in x for x in r.issues)

def test_cross_guest_invalid_types_not_clean():
    p={n:PrincipalEvidence(s,actual_sid=s,token_sid=s,elevated=0,group_sids=('not-a-sid',),acl_verified='false',independently_attested='false') for n,s in [('a','fake-a'),('b','fake-b')]}
    assert audit_cross_guest_isolation(p)

@pytest.mark.parametrize('flag',['schema2_enabled','schema_2_enabled'])
def test_boundary_rejects_schema2_alias_promotions(flag):
    report=dict(status='BLOCKED',execution_authorized=False,physical_ready=False,assurance='SYNTHETIC_ONLY',backend='MODEL',synthetic_result='PASS')
    report[flag]=True
    with pytest.raises(ContractBoundaryBlocked):audit_contracts(B.fixture(),ownership=report)

def test_boundary_does_not_promote_untrusted_fake_ownership():
    report=dict(status='BLOCKED',execution_authorized=False,physical_ready=False,assurance='SYNTHETIC_ONLY',backend='MODEL',synthetic_result='PASS')
    r=audit_contracts(B.fixture(),ownership=report)
    assert not r['provenance_verified'] and not r['execution_authorized']
    assert not r['replay_protection_verified'] and r['verified_safety_cases']==0
    assert all(c['execution']=='NOT_RUN' for c in r['guest_cases'])

def test_raw_pg_and_model_are_not_boundary_reports():
    p,a,j=P.fixtures();pg=check_pgdata_contract(p,a,j)
    with pytest.raises(ContractBoundaryBlocked):audit_contracts(B.fixture(),postgres=pg,bindings=B.bindings(B.fixture()))
    m=ReplayModel().report()
    assert m['durable_storage']=='NOT_IMPLEMENTED'
    with pytest.raises(ContractBoundaryBlocked):audit_contracts(B.fixture(),attestation=m,bindings=B.bindings(B.fixture()))

def test_independence_labels_are_not_authentication():
    claims={}
    for principal,sid in [('observer','S-1-5-21-101'),('worker','S-1-5-21-102')]:
        for i in range(2):
            claims[principal+str(i)]=EvidenceClaim(principal,principal+str(i),sid,sid,'limited',('S-1-5-32-545',),'a'*64)
    assert detect_evidence_conflicts(claims)==()  # self-labelled sources, not a signature verifier
    assert not audit_contracts(B.fixture())['provenance_verified']

def test_independent_reproduction_correlated_rollback_is_not_fixed():
    M=helper('test_vm_replay_model.py')
    m,b,n,c,v=M.prepared();cp=m.checkpoint();anchor=m.anchor
    m.consume(c,v,2,2,m.revision)
    restored=ReplayModel.recover(cp,anchor)
    restored.consume(c,v,2,2,restored.revision)  # same evidence reused after all-state rollback
    r=restored.report()
    assert r['durable_storage']=='NOT_IMPLEMENTED' and r['status']=='BLOCKED'
    assert not r['execution_authorized'] and not r['readiness_passed']

def test_vendor_pair_is_exact_and_only_overlap():
    c=json.loads((ROOT/'independent_audit/composition.json').read_text())
    assert len(c['overlap'])==2
    assert all(x['identical'] and x['prs']==['205','206'] for x in c['overlap'])

@pytest.mark.parametrize('shell',['51','7'])
def test_real_powershell_producer_to_both_pg_diagnostics(shell):
    actual=json.loads(base64.b64decode((ROOT/'independent_audit'/('producer'+shell+'.b64')).read_bytes()))
    raw=(actual['prepared']+actual['committed']).encode('utf8')
    assert actual['assessment']['byte_contract']=='MATCHED_UNAUTHENTICATED'
    r=inspect_journal_bytes(raw,actual['plan']['plan_sha256'])
    assert r['byte_contract_verified'] and r['lifecycle_phase']=='COMMITTED'
    assert not r['physical_ownership_verified'] and not r['execution_authorized']
    p,a,j=P.fixtures()
    pg=check_pgdata_contract(p,actual['plan'],raw)
    assert 'JOURNAL_PRODUCER_JSONL_NOT_DIAGNOSTIC_ENVELOPE' in pg['blockers']
    assert 'PGDATA_LAYOUT_MISMATCH' in pg['blockers']
    assert 'SCHEMA1_ADAPTER_MAPPING_BLOCKED' in pg['blockers']
    assert not pg['execution_authorized']

@pytest.mark.parametrize('payload',['a',[],None,False,{'schema':2}])
def test_pg_malformed_roots_are_blocked(payload):
    p,a,j=P.fixtures()
    r=check_pgdata_contract(p,a,payload)
    assert not r['execution_authorized'] and not r['schema2_enabled']

