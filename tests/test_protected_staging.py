"""Synthetic snapshots only: never inspect the host or import a physical adapter."""
import copy
import json
import pathlib
import ast
import subprocess
import pytest
from jsonschema import Draft202012Validator

from installer.protected_staging import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]

def fixture():
    return json.loads((ROOT/'tests/fixtures/protected_staging_synthetic.json').read_text())

def check(v):
    return validate(json.dumps(v['snapshot']), json.dumps(v['policy']))

def test_good_model_cannot_authorize_host():
    r=check(fixture())
    assert r['model_status']=='OFFLINE_MODEL_PASS'
    assert all(g['model']=='PASS' and g['host']=='BLOCKED' for g in r['gates'].values())
    assert r['HOST_VERIFIED'] is False and r['execution_authorized'] is False
    assert r['physical_tests']=='0/10 NOT_RUN' and r['physical_passes']==0

@pytest.mark.parametrize('attack',[
    'unknown_sid','group_ace','inheritance','delete_child','write_dac','write_owner',
    'reparse','source_replacement','compiler_substitution','shared_temp','evidence_overwrite',
    'missing_authorization','fake_authorization','owner','ancestor_missing','ancestor_owner',
    'ancestor_delete_child','temp_alias','temp_reused','evidence_in_temp','missing_source',
    'duplicate_path','unknown_field','bool_mask','negative_mask','null_dacl','untrusted_operator',
    'source_editor_owner','profile','toolchain_hash','cleanup','temp_not_empty','weak_evidence',
    'sid_alias','unc','relative','dotdot','ads','trailing_dot','reserved','case_alias',
    'missing_toolchain_parent','inherited_file','source_after','extra_source','commit',
])
def test_negative_snapshots(attack):
    v=fixture(); s=v['snapshot']; p=v['policy']; obj=s['objects']
    source=next(n for n in obj if n['path']==p['roots']['source'])
    leaf=next(n for n in obj if n['kind']=='FILE')
    if attack=='unknown_sid':source['aces'][2]['sid']='S-1-5-21-9-9-9-9999'
    elif attack=='group_ace':source['aces'].append(dict(sid='S-1-5-32-545',type='ALLOW',mask=1,inherited=False))
    elif attack=='inheritance':source['dacl_protected']=False
    elif attack in ('delete_child','write_dac','write_owner'):
        source['aces'][2]['mask'] |= {'delete_child':64,'write_dac':0x40000,'write_owner':0x80000}[attack]
    elif attack=='reparse':source['reparse']=True
    elif attack=='source_replacement':s['source']['hashes_at_use'][leaf['path']]='f'*64
    elif attack=='compiler_substitution':s['toolchain']['resolved_files']={r'C:\Users\User\csc.exe':'a'*64}
    elif attack=='shared_temp':s['temp']['shared']=True
    elif attack=='evidence_overwrite':s['evidence']['overwrite']=True
    elif attack=='missing_authorization':del s['authorization']
    elif attack=='fake_authorization':s['authorization']['execute']=True
    elif attack=='owner':source['owner']=p['operator_sid']
    elif attack=='ancestor_missing':obj.pop(0)
    elif attack=='ancestor_owner':obj[0]['owner']=p['operator_sid']
    elif attack=='ancestor_delete_child':obj[0]['aces'][2]['mask'] |= 64
    elif attack=='temp_alias':s['temp']['TMP']=p['roots']['temp'].lower()
    elif attack=='temp_reused':s['temp']['fresh']=False
    elif attack=='evidence_in_temp':p['roots']['evidence']=p['roots']['temp']+'\\Evidence'
    elif attack=='missing_source':obj.remove(leaf)
    elif attack=='duplicate_path':obj.append(copy.deepcopy(source))
    elif attack=='unknown_field':s['HOST_VERIFIED']=True
    elif attack=='bool_mask':source['aces'][2]['mask']=True
    elif attack=='negative_mask':source['aces'][2]['mask']=-1
    elif attack=='null_dacl':source['aces']=None
    elif attack=='untrusted_operator':p['untrusted_sids'].append(p['operator_sid'])
    elif attack=='source_editor_owner':source['owner']=p['untrusted_sids'][0]
    elif attack=='profile':s['toolchain']['profiles_disabled']=False
    elif attack=='toolchain_hash':s['toolchain']['resolved_files'][next(iter(p['toolchain_files']))]='b'*64
    elif attack=='cleanup':s['lifecycle']['cleanup_authorized']=True
    elif attack=='temp_not_empty':s['temp']['empty']=False
    elif attack=='weak_evidence':s['evidence']['exclusive_creation']=False
    elif attack=='sid_alias':p['operator_sid']='S-1-5-21-01-2-3-1005'
    elif attack in ('unc','relative','dotdot','ads','trailing_dot','reserved'):
        source['path']={'unc':r'\\server\Source','relative':r'C:Source','dotdot':r'C:\Staging\..\Source',
            'ads':r'C:\Staging\Source:ads','trailing_dot':r'C:\Staging\Source.','reserved':r'C:\Staging\CON'}[attack]
    elif attack=='case_alias':obj.append(dict(source,path=source['path'].lower()))
    elif attack=='missing_toolchain_parent':obj[:]=[n for n in obj if n['path']!=r'C:\TrustedTools']
    elif attack=='inherited_file':leaf['aces'][2]['inherited']=True
    elif attack=='source_after':s['source']['hashes_after'][leaf['path']]='0'*64
    elif attack=='extra_source':s['source']['hashes_before'][r'C:\Staging\Source\extra.ps1']='a'*64
    elif attack=='commit':s['source']['commit']='0'*40
    r=check(v)
    assert r['model_status']!='OFFLINE_MODEL_PASS'
    assert not r['HOST_VERIFIED'] and not r['execution_authorized']
    assert all(g['host']=='BLOCKED' for g in r['gates'].values())

@pytest.mark.parametrize('area,key', [('identity','sid'),('temp','fresh'),('source','custody_continuous'),
    ('toolchain','search_paths_trusted'),('evidence','fresh'),('lifecycle','unknown_contents')])
def test_unknown_is_blocked(area,key):
    v=fixture();v['snapshot'][area][key]=None
    r=check(v)
    assert r['model_status']=='BLOCKED'
    assert any(g['model']=='BLOCKED' for g in r['gates'].values())

@pytest.mark.parametrize('raw',['{}','[]','null','{"schema":1,"schema":2}', 'NaN', '\ufeff{}', '{', 'x'*65537],
    ids=['empty','array','null','duplicate','nonfinite','bom','truncated','oversized'])
def test_untrusted_json(raw):
    r=validate(raw,json.dumps(fixture()['policy']))
    assert r['model_status']=='FAIL' and not r['HOST_VERIFIED']

def test_model_digest_changes_with_input():
    v=fixture(); r=check(v); v['snapshot']['temp']['shared']=True
    assert r['snapshot_sha256']!=check(v)['snapshot_sha256']

def test_formal_schema_and_fixture():
    schema=json.loads((ROOT/'docs/protected-staging.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(fixture())
    result_schema=dict(schema, **{'$ref':'#/$defs/result'})
    # Remove input-envelope constraints before validating the output profile.
    for key in ('type','properties','required','additionalProperties'):
        result_schema.pop(key)
    Draft202012Validator(result_schema).validate(check(fixture()))

@pytest.mark.parametrize('mutation',['unknown','type','required','mask','extra_ace'])
def test_schema_is_closed(mutation):
    schema=json.loads((ROOT/'docs/protected-staging.schema.json').read_text()); v=fixture()
    if mutation=='unknown':v['policy']['host_verified']=True
    elif mutation=='type':v['snapshot']['temp']['fresh']='true'
    elif mutation=='required':del v['snapshot']['authorization']
    elif mutation=='mask':v['snapshot']['objects'][0]['aces'][0]['mask']=True
    elif mutation=='extra_ace':v['snapshot']['objects'][0]['aces'].append(v['snapshot']['objects'][0]['aces'][0])
    assert list(Draft202012Validator(schema).iter_errors(v))

def test_validator_has_no_host_capability_surface():
    tree=ast.parse((ROOT/'installer/protected_staging.py').read_text())
    imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
            assert node.func.id not in ('open','eval','exec','compile','__import__','getattr')
    assert sorted(imports)==['hashlib','installer.vm_lab_json','ntpath','re']

def test_inherited_physical_sources_are_frozen():
    base='2a93efaab1ec61cc5e2a872b95e47a0a8a227f55'
    for folder in ('lab/pc4','lab/lsa-readonly'):
        paths=subprocess.check_output(['git','ls-tree','-r','--name-only',base,folder],cwd=ROOT).decode().splitlines()
        assert paths
        for name in paths:
            original=subprocess.check_output(['git','show',f'{base}:{name}'],cwd=ROOT)
            assert original.replace(b'\r\n',b'\n')==(ROOT/name).read_bytes().replace(b'\r\n',b'\n')

def test_specialized_workflow_never_runs_physical_tools():
    text=(ROOT/'.github/workflows/protected-staging-offline.yml').read_text()
    assert 'self-hosted' not in text and 'services:' not in text
    for forbidden in ('CollectLocal','Add-Type','Invoke-Command','initdb','Set-Acl','Start-Service','ssh '):
        assert forbidden not in text
    assert 'github.event.pull_request.head.sha || github.sha' in text
    assert 'staging-offline.xml' in text and 'tools/check_staging_offline.py' in text

@pytest.mark.parametrize('kind',['NETWORK','REMOVABLE','UNKNOWN',None])
def test_non_fixed_volume_rejected(kind):
    v=fixture();v['snapshot']['volume']['kind']=kind
    assert check(v)['model_status']=='FAIL'

def test_volume_identity_replacement():
    v=fixture();v['snapshot']['volume']['identity']='replacement'
    assert check(v)['gates']['S2']['model']=='FAIL'

def test_fail_dominates_blocked():
    v=fixture();v['snapshot']['identity']['sid']=None;v['snapshot']['temp']['shared']=True
    r=check(v)
    assert r['gates']['S1']['model']=='BLOCKED' and r['model_status']=='FAIL'

@pytest.mark.parametrize('value',[0,1,'false',[],{}])
def test_type_confused_boolean(value):
    v=fixture();v['snapshot']['authorization']['execute']=value
    assert check(v)['gates']['S1']['model']=='FAIL'

def test_replay_is_not_host_evidence():
    v=fixture();first=check(v);second=check(v)
    assert first==second and first['model_status']=='OFFLINE_MODEL_PASS'
    assert not second['HOST_VERIFIED'] and not second['execution_authorized']

def test_current_branch_cannot_enter_infrastructure_jobs():
    import re
    branch='audit/protected-staging-offline-20261022'
    positives={'pc4-sid-acl-offline.yml','pgdata-intent-offline.yml','lab-airgap-a.yml',
        'lab-witness-l1.yml','windows-lab-planning.yml','offline-rc-review.yml','protected-staging-offline.yml'}
    for p in (ROOT/'.github/workflows').glob('*.yml'):
        text=p.read_text()
        for job in re.split(r'(?m)^  [A-Za-z0-9_-]+:\n',text.split('jobs:\n',1)[1])[1:]:
            first=job.splitlines()[0]
            if p.name in positives:
                assert "github.head_ref == '" in first and "github.ref_name == '" in first
                assert 'services:' not in text and 'self-hosted' not in text
            else:
                assert f"github.head_ref != '{branch}'" in first and f"github.ref_name != '{branch}'" in first
