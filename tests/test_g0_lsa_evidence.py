"""Synthetic LSA snapshots only: never call Windows policy/token APIs."""
import copy
import pytest
from installer import g0_lsa_evidence as e
HEAD='a'*40
RUN='b'*32
PINS={'GridLabCollector':'S-1-5-21-1-2-3-1003','GridLabStorage':'S-1-5-21-1-2-3-1004'}
RIGHTS=['SeInteractiveLogonRight','SeRemoteInteractiveLogonRight','SeNetworkLogonRight','SeBatchLogonRight','SeServiceLogonRight','SeDenyInteractiveLogonRight','SeDenyRemoteInteractiveLogonRight','SeDenyNetworkLogonRight','SeDenyBatchLogonRight','SeDenyServiceLogonRight']
def snapshot():
    subjects=[]
    for name,sid in PINS.items():
        subjects.append(dict(name=name,expected_sid=sid,observed_sid=sid,state='DIRECT_ONLY',code='ENUMERATED',ntstatus=0,win32=0,cleanup_failed=False,rights=['SeBatchLogonRight'],logon_rights={r:('ASSIGNED_DIRECT' if r=='SeBatchLogonRight' else 'NOT_DIRECTLY_ASSIGNED') for r in RIGHTS}))
    return dict(schema='grid-g0-lsa-1',head=HEAD,run_id=RUN,host='PC4',mode='MemoryReadOnly',collection='DIRECT_POLICY_OBSERVED',subjects=subjects,effective_rights='UNKNOWN',group_completeness='UNKNOWN',execution_authorized=False,cleanup_authorized=False,host_verified=False,actor_tokens_created=False,physical_tests='0/10 NOT_RUN')
def check(v):return e.validate(v,head=HEAD,run_id=RUN,expected_sids=PINS)
def test_direct_only_never_effective():assert check(snapshot())=='DIRECT_POLICY_OBSERVED'
@pytest.mark.parametrize('field,value',[('head','c'*40),('run_id','c'*32),('host','LS5'),('execution_authorized',True),('cleanup_authorized',1),('host_verified',True),('actor_tokens_created',True),('physical_tests','10/10 PASS'),('effective_rights','PASS'),('group_completeness','COMPLETE'),('schema','other'),('mode','Execute'),('extra',None)])
def test_context_or_authority_tamper(field,value):
    v=snapshot();v[field]=value
    with pytest.raises(ValueError):check(v)
@pytest.mark.parametrize('case',['missing','duplicate','swapped','sid-mismatch','sid-noncanonical','wrong-name','access-denied','unknown','cleanup','bool-status','status-overflow','unknown-code','duplicate-right','unknown-right','missing-deny','false-map','extra-row-field'])
def test_incomplete_or_substituted_subject(case):
    v=snapshot();r=v['subjects'][0]
    if case=='missing':v['subjects'].pop()
    elif case=='duplicate':v['subjects'][1]=copy.deepcopy(r)
    elif case=='swapped':r['observed_sid']=PINS['GridLabStorage']
    elif case=='sid-mismatch':r['observed_sid']=r['observed_sid'][:-1]+'5'
    elif case=='sid-noncanonical':r['expected_sid']='s'+r['expected_sid'][1:]
    elif case=='wrong-name':r['name']='someone'
    elif case=='access-denied':r['ntstatus']=0xC0000022;r['win32']=5
    elif case=='unknown':r['state']='UNKNOWN'
    elif case=='cleanup':r['cleanup_failed']=True
    elif case=='bool-status':r['ntstatus']=False
    elif case=='status-overflow':r['ntstatus']=2**32
    elif case=='unknown-code':r['code']='IGNORED_ERROR'
    elif case=='duplicate-right':r['rights']*=2
    elif case=='unknown-right':r['rights']=['SeMadeUpRight']
    elif case=='missing-deny':r['logon_rights'].pop('SeDenyBatchLogonRight')
    elif case=='false-map':r['logon_rights']['SeBatchLogonRight']='NOT_DIRECTLY_ASSIGNED'
    else:r['extra']=True
    with pytest.raises(ValueError):check(v)
@pytest.mark.parametrize('code',['OPEN_FAILED','ENUMERATE_FAILED','CLEANUP_FAILED','SID_MISMATCH'])
def test_error_snapshot_remains_blocked(code):
    v=snapshot();v['collection']='BLOCKED';r=v['subjects'][0];r.update(state='UNKNOWN',code=code,ntstatus=0xC0000022,win32=5,rights=[],logon_rights={x:'UNKNOWN' for x in RIGHTS},cleanup_failed=code=='CLEANUP_FAILED')
    if code=='SID_MISMATCH':r['observed_sid']=None
    assert check(v)=='BLOCKED'
def test_corrupted_zero_count_no_direct_status():
    v=snapshot();r=v['subjects'][0];r.update(code='NO_DIRECT_ASSIGNMENTS',ntstatus=0xC0000034,win32=2)
    with pytest.raises(ValueError):check(v)

@pytest.mark.parametrize('part',['4294967296','9999999999'])
def test_sid_subauthority_overflow(part):
    v=snapshot();pins={n:x.replace('-1-2-3-',f'-{part}-2-3-') for n,x in PINS.items()}
    for r in v['subjects']:r['expected_sid']=r['observed_sid']=pins[r['name']]
    with pytest.raises(ValueError):e.validate(v,head=HEAD,run_id=RUN,expected_sids=pins)
def test_uint32_maximum_subauthority():
    v=snapshot();pins={n:x.replace('-1-2-3-','-4294967295-2-3-') for n,x in PINS.items()}
    for r in v['subjects']:r['expected_sid']=r['observed_sid']=pins[r['name']]
    assert e.validate(v,head=HEAD,run_id=RUN,expected_sids=pins)=='DIRECT_POLICY_OBSERVED'

def test_memory_entry_has_no_compiler_or_mutation_surface():
    from pathlib import Path
    s=(Path(__file__).parents[1]/'lab/lsa-readonly/Read-G0LsaMemory.ps1').read_text()
    for forbidden in ['Add-Type','LogonUser','CreateProcess','AdjustTokenPrivileges','Set-Acl','Set-LocalUser','Start-Service','WriteAll','Start-Process','SetEnvironmentVariable']:
        assert forbidden not in s
    assert s.index('if(-not $CollectMemory)')<s.index('Import-Module')<s.index('if(-not $binding.complete)')<s.index('[Reflection.Assembly]::Load')
def test_build_and_fake_test_refuse_pc4_before_effects():
    from pathlib import Path
    root=Path(__file__).parents[1]/'lab/lsa-readonly'
    for filename,effect in [('Build-G0Memory.ps1','Add-Type'),('Test-G0Memory.ps1','[Reflection.Assembly]::Load')]:
        s=(root/filename).read_text();assert s.index("MachineName -ieq 'PC4'")<s.index(effect)
def test_native_surface_system32_only():
    from pathlib import Path
    s=(Path(__file__).parents[1]/'lab/lsa-readonly/LsaRights.cs').read_text()
    assert s.count('DllImport("advapi32.dll")')==5
    assert s.count('DefaultDllImportSearchPaths(DllImportSearchPath.System32)')==5
