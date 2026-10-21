"""Synthetic evidence format tests. Never run PC4 or native collectors."""
import copy
import hashlib
import json
import pytest
from installer.pc4_sid_acl_evidence import validate, render_junit

RUN = '77777777-7777-4777-8777-777777777777'
SIDS = {'Collector':'S-1-5-21-1-2-3-1003', 'Storage':'S-1-5-21-1-2-3-1004'}
CASES = ('token','own_write','own_read','foreign_read_denied','foreign_write_denied')

def fixture():
    records=[]
    for role in SIDS:
        for case in CASES:
            records.append(dict(schema=1,source='NATIVE_PC4_LOCAL',run_id=RUN,role=role,
                case=case,outcome='PASS',code='ACCESS_DENIED_5' if case.startswith('foreign_') else 'OK',pid=100 if role=='Collector' else 101,
                facts=dict(sid=SIDS[role],admin_group=False,elevated=False,integrity_rid=8192,
                    impersonating=False,privileges=[dict(name='SeChangeNotifyPrivilege',enabled=True)]) if case=='token' else None))
    raw=''.join(json.dumps(r,separators=(',',':'))+'\n' for r in records)
    return raw,hashlib.sha256(raw.encode()).hexdigest()

def test_format_pass_is_not_physical_attestation():
    raw,digest=fixture();r=validate(raw,expected_run=RUN,expected_sids=SIDS,expected_sha256=digest)
    assert r['format_valid'] and r['reported_passes']==10
    assert not r['physical_attestation'] and not r['airgap_verified']
    assert not r['execution_authorized'] and not r['readiness_passed']
    assert 'tests="10"' in render_junit(r)

@pytest.mark.parametrize('mutation',['missing','duplicate','run','sid','admin','elevated','integrity',
    'privilege','enabled_extra','impersonation','pid','same_pid','unexpected_case','skipped',
    'facts_extra','root_extra','foreign_error','native_missing','bool_pid','fake_source'])
def test_spoofed_or_incomplete_evidence(mutation):
    raw,_=fixture();v=[json.loads(x) for x in raw.splitlines()]
    if mutation=='missing':v.pop()
    elif mutation=='duplicate':v[-1]=v[0]
    elif mutation=='run':v[0]['run_id']='88888888-8888-4888-8888-888888888888'
    elif mutation=='sid':v[0]['facts']['sid']=SIDS['Storage']
    elif mutation=='admin':v[0]['facts']['admin_group']=True
    elif mutation=='elevated':v[0]['facts']['elevated']=True
    elif mutation=='integrity':v[0]['facts']['integrity_rid']=12288
    elif mutation=='privilege':v[0]['facts']['privileges'].append(dict(name='SeDebugPrivilege',enabled=False))
    elif mutation=='enabled_extra':v[0]['facts']['privileges'].append(dict(name='SeShutdownPrivilege',enabled=True))
    elif mutation=='impersonation':v[0]['facts']['impersonating']=True
    elif mutation=='pid':v[1]['pid']=999
    elif mutation=='same_pid':
        for r in v:r['pid']=100
    elif mutation=='unexpected_case':v[0]['case']='other'
    elif mutation=='skipped':v[0]['outcome']='SKIP'
    elif mutation=='facts_extra':v[0]['facts']['trusted']=True
    elif mutation=='root_extra':v[0]['password']='SENSITIVE_SENTINEL'
    elif mutation=='foreign_error':v[-1]['code']='FILE_NOT_FOUND';v[-1]['outcome']='FAIL'
    elif mutation=='native_missing':v[0]['facts']=None
    elif mutation=='bool_pid':v[0]['pid']=True
    else:v[0]['source']='SYNTHETIC'
    raw=''.join(json.dumps(r)+'\n' for r in v)
    r=validate(raw,expected_run=RUN,expected_sids=SIDS,expected_sha256=hashlib.sha256(raw.encode()).hexdigest())
    assert not r['format_valid'] or r['reported_passes']<10
    assert not r['physical_attestation']
    assert 'SENSITIVE_SENTINEL' not in json.dumps(r)+render_junit(r)

@pytest.mark.parametrize('raw',['{}','null\n','NaN\n','{"a":1,"a":2}\n','\ud800','x'*131073],ids=['object','null','nonfinite','duplicate','surrogate','oversized'])
def test_bad_bytes(raw):
    r=validate(raw,expected_run=RUN,expected_sids=SIDS,expected_sha256='0'*64)
    assert not r['format_valid']
    assert 'failures="1"' in render_junit(r)

def test_digest_identity_and_expected_scope_required():
    raw,d=fixture()
    for sids in ({}, {'Collector':SIDS['Collector'],'Storage':SIDS['Collector']}, {'Collector':'1003','Storage':'1004'}, {'Collector':SIDS['Collector'],'Storage':'S-1-5-21-4-5-6-1004'}):
        assert not validate(raw,expected_run=RUN,expected_sids=sids,expected_sha256=d)['format_valid']
    assert not validate(raw,expected_run=RUN,expected_sids=SIDS,expected_sha256='a'*64)['format_valid']

def test_partial_failure_junit_never_false_green():
    raw,_=fixture();v=[json.loads(x) for x in raw.splitlines()]
    v[3]['outcome']='FAIL';v[3]['code']='ACCESS_UNEXPECTEDLY_ALLOWED'
    raw=''.join(json.dumps(r)+'\n' for r in v)
    r=validate(raw,expected_run=RUN,expected_sids=SIDS,expected_sha256=hashlib.sha256(raw.encode()).hexdigest())
    assert r['format_valid'] and r['reported_passes']==9
    assert 'failures="1"' in render_junit(r)

def test_invalid_scope_never_echoes_secrets():
    raw,d=fixture()
    r=validate(raw,expected_run='SENSITIVE_SENTINEL',expected_sids=SIDS,expected_sha256=d)
    assert not r['format_valid'] and 'SENSITIVE_SENTINEL' not in str(r)+render_junit(r)

def test_package_default_and_physical_limits_are_explicit():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    script=(root/'lab/pc4/Invoke-Pc4SidAcl.ps1').read_text()
    default=script.split(". (Join-Path $PSScriptRoot 'Common.ps1')",1)[0]
    assert "if(!$Execute -and !$Cleanup)" in default and "mode='PlanOnly'" in default
    for forbidden in ('Enable-LocalUser','Set-LocalUser','Set-Acl','Set-ExecutionPolicy','Stop-Service','-ExecutionPolicy Bypass','-Recurse'):
        assert forbidden not in script
    assert '$start.Password=$credentials[$role].Password' in script
    arguments=next(x for x in script.splitlines() if '$start.Arguments=' in x)
    assert 'Password' not in arguments and 'password' not in arguments
    assert 'PC4_LOCAL_ONLY' in script and 'SEPARATE_ACCOUNT_PLAN_AND_FIXTURE_APPROVAL_REQUIRED' in script
    actor=(root/'lab/pc4/Actor.ps1').read_text()
    assert "($e.HResult -band 0xffff) -eq 5" in actor
    assert "TokenFacts.dll'" in actor and 'Add-Type -Path $assembly' in actor

def test_new_workflow_excludes_all_inherited_jobs():
    from pathlib import Path
    import re
    root=Path(__file__).resolve().parents[1]
    positive={'pc4-sid-acl-offline.yml':'audit/codex-pc4-sid-acl-20261021',
              'pgdata-intent-offline.yml':'planning/pgdata-intent-v1-20261021',
              'lab-airgap-a.yml':'planning/lab-airgap-a-20261021',
              'lab-witness-l1.yml':'planning/lab-witness-l1-20261020',
              'windows-lab-planning.yml':'planning/windows-lab-l0-20261020',
              'offline-rc-review.yml':'review/offline-rc-20261020'}
    for p in (root/'.github/workflows').glob('*.yml'):
        text=p.read_text()
        for job in re.split(r'(?m)^  [A-Za-z0-9_-]+:\n',text.split('jobs:\n',1)[1])[1:]:
            first=job.splitlines()[0]
            if p.name in positive:
                b=positive[p.name]
                assert "github.head_ref == '"+b+"'" in first
                assert "github.ref_name == '"+b+"'" in first
                assert 'services:' not in text and 'self-hosted' not in text
            else:
                assert "github.head_ref != 'audit/codex-pc4-sid-acl-20261021'" in first
                assert "github.ref_name != 'audit/codex-pc4-sid-acl-20261021'" in first
