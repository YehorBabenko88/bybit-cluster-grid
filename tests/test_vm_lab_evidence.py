"""Future evidence draft integrity is NOT observer authentication."""
import copy
import json
import re
import pytest
from pathlib import Path


def plan():
    return json.loads((Path(__file__).resolve().parents[1]/'installer/tests/vm-lab-plan.example.json').read_text(encoding='utf-8'))


def test_integrity_match_does_not_authenticate_or_authorize():
    from installer.vm_lab_evidence import draft, inspect_evidence
    p=plan();e=draft(p,'55555555-5555-4555-8555-555555555555')
    r=inspect_evidence(json.dumps(e),p)
    assert r['integrity']=='MATCH_METADATA_ONLY' and r['authentication']=='UNVERIFIED'
    assert r['status']=='BLOCKED' and not r['readiness_passed'] and not r['execution_authorized']
    assert len(r['negative_cases'])==12 and all(c['execution']=='NOT_RUN' for c in r['negative_cases'])


@pytest.mark.parametrize('mutation', ['payload','plan','missing','duplicate','pass','skip','approval','token','signature','hash','quotas'])
def test_supplied_evidence_cannot_promote_readiness_even_if_rehashed(mutation):
    from installer.vm_lab_evidence import draft, inspect_evidence, digest
    p=plan();e=draft(p,'55555555-5555-4555-8555-555555555555')
    if mutation=='payload':e['payload']['vm_id']='66666666-6666-4666-8666-666666666666'
    elif mutation=='plan':e['plan_sha256']='d'*64
    elif mutation=='missing':e['payload']['negative_cases'].pop()
    elif mutation=='duplicate':e['payload']['negative_cases'][-1]=copy.deepcopy(e['payload']['negative_cases'][0])
    elif mutation=='pass':e['payload']['negative_cases'][0]['execution']='PASS'
    elif mutation=='skip':e['payload']['negative_cases'][0]['execution']='SKIPPED'
    elif mutation=='approval':e['payload']['approval_evidence']='APPROVED'
    elif mutation=='token':e['payload']['identity_evidence']='ATTESTED'
    elif mutation=='signature':e['signature']='forged'
    elif mutation=='hash':e['payload_sha256']='e'*64
    elif mutation=='quotas':e['payload']['quotas']['cpu']=True
    if mutation!='hash':e['payload_sha256']=digest(e['payload'])
    with pytest.raises(ValueError):inspect_evidence(json.dumps(e),p)


def test_whitespace_does_not_change_canonical_binding_but_plan_change_does():
    from installer.vm_lab_evidence import draft, inspect_evidence
    p=plan();e=draft(p,'55555555-5555-4555-8555-555555555555')
    assert inspect_evidence(json.dumps(e,indent=2),p)['status']=='BLOCKED'
    p['quotas']['cpu']=3
    with pytest.raises(ValueError):inspect_evidence(json.dumps(e),p)


def test_duplicate_json_and_nonobject_fail_closed():
    from installer.vm_lab_evidence import inspect_evidence
    for raw in ('[]','{"schema":1,"schema":1}', '"😀"'):
        with pytest.raises(ValueError):inspect_evidence(raw,plan())


def test_evidence_type_mutations_never_escape_or_authorize():
    from installer.vm_lab_evidence import draft,inspect_evidence
    p=plan();base=draft(p,'55555555-5555-4555-8555-555555555555');paths=[]
    def walk(value,path=()):
        paths.append(path)
        if type(value) is dict:
            for k,v in value.items():walk(v,path+(k,))
        elif type(value) is list:
            for k,v in enumerate(value):walk(v,path+(k,))
    walk(base)
    for path in paths:
        for replacement in (None,True,1,1.5,'x','😀',[],{}):
            value=copy.deepcopy(base)
            if not path:value=replacement
            else:
                target=value
                for k in path[:-1]:target=target[k]
                target[path[-1]]=replacement
            try:r=inspect_evidence(json.dumps(value),p)
            except ValueError as exc:assert re.fullmatch('VM_[A-Z_]{1,64}',str(exc))
            else:assert not r['readiness_passed'] and not r['execution_authorized']
