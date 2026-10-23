import copy
import pytest
from installer.ls5_acl_ci import NATIVE_CASES,verify_native


def rows():
    return [dict(case=c,outcome='PASS',head='a'*40,run_id='123',attempt='1',scope='HOSTED_GUID_ACL_LAYOUT_ONLY',
        host_verified=False,physical_attestation=False,execute_authorized=False,cleanup_authorized=False) for c in NATIVE_CASES]


def test_correct_native_receipt_remains_non_physical():
    verify_native(rows(),'a'*40,'123','1')


@pytest.mark.parametrize('fault',['missing','duplicate','head','run','attempt','fail','physical','execute','cleanup','unknown','numeric-false'])
def test_forged_native_receipt_is_rejected(fault):
    r=copy.deepcopy(rows())
    if fault=='missing':r.pop()
    if fault=='duplicate':r[-1]=r[0]
    if fault=='head':r[0]['head']='b'*40
    if fault=='run':r[0]['run_id']='124'
    if fault=='attempt':r[0]['attempt']='2'
    if fault=='fail':r[0]['outcome']='SKIP'
    if fault=='physical':r[0]['physical_attestation']=True
    if fault=='execute':r[0]['execute_authorized']=True
    if fault=='cleanup':r[0]['cleanup_authorized']=True
    if fault=='unknown':r[0]['extra']='PASS'
    if fault=='numeric-false':r[0]['host_verified']=0
    with pytest.raises(ValueError):verify_native(r,'a'*40,'123','1')


@pytest.mark.parametrize('fault',['failure','error','skipped','count','case'])
def test_junit_cannot_claim_false_pass(tmp_path,fault):
    from installer.ls5_acl_ci import verify_junit
    text='<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="c" name="n"/></testsuite>'
    if fault in ('failure','error','skipped'):text=text.replace('/>',f'><{fault}/></testcase>')
    if fault=='count':text=text.replace('tests="1"','tests="2"')
    if fault=='case':text=text.replace('name="n"','name="wrong"')
    p=tmp_path/'junit.xml';p.write_text(text)
    with pytest.raises(ValueError):verify_junit(p,['node'],[['c','n']])
