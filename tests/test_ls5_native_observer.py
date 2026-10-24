from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]


def test_observer_requires_relative_no_follow_chain():
    source='\n'.join(p.read_text(encoding='utf-8-sig') for p in (ROOT/'installer/native-acl-observer').glob('*.cs'))
    for api in ['NtCreateFile','RootDirectory','OBJ_DONT_REPARSE','GetSecurityInfo','AccessCheck','DuplicateTokenEx','GetTokenInformation']:
        assert api in source
    for forbidden in ['SetSecurityInfo','SetNamedSecurityInfo','AdjustTokenPrivileges','LogonUser','CreateProcess']:
        assert forbidden not in source


def test_ci_exact_head_and_receipts_required():
    s=(ROOT/'.github/workflows/ls5-native-observer.yml').read_text()
    for marker in ['github.event.pull_request.head.sha','required-observer-gate','--verify','JSONL','SHA256']:
        assert marker in s
    assert 'Remove-Item' not in s and 'fetch-depth: 0' in s


def test_executor_authority_stays_blocked():
    s=(ROOT/'installer/ls5-acl-remediation.ps1').read_text()
    assert "if($Apply){throw 'EXECUTE_NOT_AUTHORIZED" in s


def receipt():
    import hashlib,json
    token=dict(user='S-1-5-21-1-2-3-1001',elevated=True,integrity=12288,groups=[dict(sid='S-1-1-0',attributes=4)])
    raw=dict(user=token['user'],elevated=True,level=12288,groups=[dict(Sid='S-1-1-0',Attributes=4)])
    token['fingerprint']=hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest().upper()
    chain=[dict(depth=i,identity=dict(volume=1,fileId=f'{i+1:032X}',links=1,attributes=16 if i<3 else 0),
        owner='S-1-5-18',group='S-1-5-18',descriptorSha256='A'*64,protected=True,
        aces=[dict(sid='S-1-5-18',mask=0x1f01ff,flags=0,type='AccessAllowed')],
        effectiveRights={k:'DACL_ALLOW' for k in ['DELETE','WRITE_DAC','WRITE_OWNER','WRITE_DATA','APPEND_DATA','DELETE_CHILD']}) for i in range(4)]
    report=dict(fault_injection=False,status='BLOCKED',observation='OBSERVED',effectiveRightsStatus='BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN',token=token,chain=chain)
    flags={k:False for k in ['physical_attestation','host_verified','apply_authorized','execute_authorized','cleanup_authorized']}
    report.update(flags)
    return dict(case='ordinary-read-only-observation',head='a'*40,run_id='1',attempt='1',outcome='PASS',kind='HOSTED_GUID_OBSERVER_TEST',payload=dict(code=0,value=report),details=None,**flags)


def test_valid_receipt_has_no_authority():
    from installer.native_observer_ci import verify_rows
    r=receipt();verify_rows([r],[r['case']],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['missing-token','bad-group-flags','token-digest','ace-sid','ace-kind','ace-bool-mask'])
def test_native_receipt_rejects_unknown_security_facts(fault):
    from installer.native_observer_ci import verify_rows
    r=receipt();v=r['payload']['value']
    if fault=='missing-token':del v['token']
    if fault=='bad-group-flags':v['token']['groups'][0]['attributes']=0x14
    if fault=='token-digest':v['token']['fingerprint']='B'*64
    if fault=='ace-sid':v['chain'][0]['aces'][0]['sid']='BUILTIN\\Users'
    if fault=='ace-kind':v['chain'][0]['aces'][0]['type']='Callback'
    if fault=='ace-bool-mask':v['chain'][0]['aces'][0]['mask']=True
    with pytest.raises(ValueError):verify_rows([r],[r['case']],'a'*40,'1','1')


@pytest.mark.parametrize('fault',['row-authority','report-authority','wrong-head','wrong-run','wrong-attempt','bool-exit','no-chain','symlink','hardlink','missing-right','native-error','skip'])
def test_native_evidence_forgery_is_rejected(fault):
    from installer.native_observer_ci import verify_rows
    r=receipt();v=r['payload']['value']
    if fault=='row-authority':r['host_verified']=True
    if fault=='report-authority':v['apply_authorized']=True
    if fault=='wrong-head':r['head']='b'*40
    if fault=='wrong-run':r['run_id']='2'
    if fault=='wrong-attempt':r['attempt']='2'
    if fault=='bool-exit':r['payload']['code']=False
    if fault=='no-chain':v['chain']=[]
    if fault=='symlink':v['chain'][0]['identity']['attributes']|=0x400
    if fault=='hardlink':v['chain'][-1]['identity']['links']=2
    if fault=='missing-right':del v['chain'][0]['effectiveRights']['WRITE_DAC']
    if fault=='native-error':r['payload']['code']=2
    if fault=='skip':r['outcome']='SKIP'
    with pytest.raises(ValueError):verify_rows([r],[r['case']],'a'*40,'1','1')
