"""Injected read-only profile resolution; never a physical observation."""
import pytest
from s0_smoke.profile import validate_profile_paths, parent_path
from s0_smoke.windows import WindowsBlocked


def test_profile_path_requires_both_api_results_and_os_volume():
    assert validate_profile_paths(r'C:\Users\fixture', r'C:\Users\fixture', 'C:\\') == r'C:\Users\fixture'


@pytest.mark.parametrize('path', [r'\\server\profile', r'\\?\C:\Users\fixture',
                                 r'D:\Users\fixture', r'C:\Users\..\fixture',
                                 r'C:\Users\CON', 'C:\\Users\\COM¹', r'C:\Users\fixture.',
                                 r'C:\Users\fix~1', '', None, 'C:\\'+'a'*241])
def test_profile_path_aliases_and_unknown_results_are_blocked(path):
    with pytest.raises(WindowsBlocked): validate_profile_paths(path,path,'C:\\')


def test_profile_path_mismatch_is_not_an_environment_fallback():
    with pytest.raises(WindowsBlocked): validate_profile_paths(r'C:\Users\one',r'C:\Users\two','C:\\')


def test_explicit_profile_resolution_does_not_use_localappdata(monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',r'C:\untrusted')
    class Api:
        def user_profile_v1(self,sid):
            assert sid == 'S-1-5-21-1-2-3-1002'
            return r'C:\Users\fixture'
    assert parent_path('UserProfileV1','S-1-5-21-1-2-3-1002',api=Api()) == r'C:\Users\fixture'


@pytest.mark.parametrize('mode', ['fallback', 'UserProfile', '', None, True])
def test_unknown_parent_contract_is_blocked(mode):
    with pytest.raises(WindowsBlocked): parent_path(mode,'S-1-5-21-1-2-3-1002')


def test_same_identity_acl_drift_is_not_accepted():
    from test_s0_windows import Fake, acl
    from s0_smoke.windows import Custody
    api=Fake(); original=api.inspect
    with Custody(r'C:\safe','S-1-5-1000',api=api,_strict_root=False) as lease:
        def changed(handle):
            result=original(handle);result['acl']=acl(mask=0x20);return result
        api.inspect=changed
        with pytest.raises(WindowsBlocked):lease.guard()


@pytest.mark.parametrize('mask',[0x10,0x100])
def test_v1_ancestor_attribute_write_is_blocked_without_changing_legacy(mask):
    from test_s0_windows import Fake,acl,sid
    from s0_smoke.windows import Custody
    api=Fake();original=api.inspect
    def attribute_write(handle):
        info=original(handle);info['acl']=acl(mask=mask,who=sid(2000));return info
    api.inspect=attribute_write
    with Custody(r'C:\safe','S-1-5-1000',api=api,_strict_root=False):pass
    with pytest.raises(WindowsBlocked):
        with Custody(r'C:\safe','S-1-5-1000',api=api,_strict_root=False,_profile_v1=True):pass


def profile_record():
    from tools.s0_userprofile_receipt import CORE_CASES
    return dict(scope='HOSTED_NATIVE_USER_PROFILE_CORE_NOT_PHYSICAL',head='a'*40,package_sha256='b'*64,fixture_id='s0-portable-12345678-1234-4234-8234-123456789abc',
                cases=sorted(CORE_CASES),pid=100,creation_filetime=1000,exit_code=0,deadline_pid=101,
                deadline_exit_code=1,deadline_timed_out=True,execute=False,cleanup=False)

def runtime_record():
    from tools.s0_userprofile_receipt import RUNTIME_CASES
    return dict(scope='HOSTED_NATIVE_USER_PROFILE_RUNTIME_NOT_PHYSICAL',head='a'*40,package_sha256='b'*64,fixture_id='s0-portable-12345678-1234-4234-8234-123456789abc',
                run_id='123',attempt='1',cases=sorted(RUNTIME_CASES),execute=False,cleanup=False)


def test_full_profile_receipt_cannot_be_collected_without_runtime_phase(tmp_path):
    import json
    from tools.s0_userprofile_receipt import collect_profile
    fixture=tmp_path/'fixture';(fixture/'temp').mkdir(parents=True)
    (fixture/'temp/user-profile.json').write_text(json.dumps(profile_record()))
    out=tmp_path/'out';out.mkdir()
    with pytest.raises(FileNotFoundError):
        collect_profile(out,fixture,dict(head='a'*40,run_id='123',attempt='1'),'b'*64)


@pytest.mark.parametrize('key,value', [('pid',True),('pid',0),('creation_filetime',None),
                                    ('deadline_timed_out',1),('deadline_exit_code',259),
                                    ('execute',0),('cleanup',True),('head','c'*40),
                                    ('scope','PHYSICAL_PASS'),('cases',[])])
def test_native_profile_receipt_unknown_or_substituted_facts_block(key,value):
    import json
    from tools.s0_userprofile_receipt import validate_profile_raw
    record=profile_record();record[key]=value
    with pytest.raises(ValueError):validate_profile_raw(json.dumps(record).encode(),'a'*40,'b'*64)


@pytest.mark.parametrize('mutation',['head','attempt','junit_text','jsonl_boolean','missing','runtime_attempt','runtime_missing','record_boolean','runtime_fixture'])
def test_profile_bundle_does_not_accept_rehashed_false_pass(tmp_path,mutation):
    import json,hashlib
    from tools.s0_userprofile_receipt import collect_profile,verify_profile_bundle
    context=dict(head='a'*40,run_id='123',attempt='1')
    fixture=tmp_path/'fixture';(fixture/'temp').mkdir(parents=True)
    (fixture/'temp/user-profile.json').write_text(json.dumps(profile_record()))
    (fixture/'temp/user-profile-runtime.json').write_text(json.dumps(runtime_record()))
    out=tmp_path/'out';out.mkdir();collect_profile(out,fixture,context,'b'*64)
    read=lambda name:(out/name).read_bytes()
    assert verify_profile_bundle(read,context,'b'*64)['pid']==100
    record=json.loads(read('native-userprofile.json'))
    if mutation in ('head','attempt'):record[mutation]='c'*40 if mutation=='head' else '2'
    elif mutation=='junit_text':
        value=read('native-userprofile.xml').replace(b'</testsuite>',b'INJECTED</testsuite>')
        (out/'native-userprofile.xml').write_bytes(value);record['junit_sha256']=hashlib.sha256(value).hexdigest()
    elif mutation=='jsonl_boolean':
        rows=[json.loads(row) for row in read('native-userprofile.jsonl').splitlines()]
        rows[0]['execute']=0;value=b''.join((json.dumps(row)+'\n').encode() for row in rows)
        (out/'native-userprofile.jsonl').write_bytes(value);record['jsonl_sha256']=hashlib.sha256(value).hexdigest()
    elif mutation=='runtime_attempt':
        value=runtime_record();value['attempt']='2';data=json.dumps(value).encode()
        (out/'native-userprofile-runtime.json').write_bytes(data);record['runtime_sha256']=hashlib.sha256(data).hexdigest()
    elif mutation=='runtime_missing':(out/'native-userprofile-runtime.json').unlink()
    elif mutation=='runtime_fixture':
        value=runtime_record();value['fixture_id']='s0-portable-12345678-1234-4234-8234-123456789abd';data=json.dumps(value).encode()
        (out/'native-userprofile-runtime.json').write_bytes(data);record['runtime_sha256']=hashlib.sha256(data).hexdigest()
    elif mutation=='record_boolean':record['execute']=0
    else:(out/'native-userprofile.xml').unlink()
    (out/'native-userprofile.json').write_text(json.dumps(record))
    with pytest.raises((ValueError,FileNotFoundError)):verify_profile_bundle(read,context,'b'*64)


def test_profile_transfer_plan_is_explicit_and_never_authorizes():
    from test_s0_ssh_transfer_plan import record
    from tools.s0_ssh_transfer_plan import build_transfer_plan_at_user_profile_v1
    data=record()
    for key in ('source_known_folder','source_root','source_path','recipient_known_folder','recipient_root','recipient_path'):
        data[key]=data[key].replace(r'\AppData\Local','')
    data.update(parent_scope='UserProfileV1',source_parent_identity='1234abcd:0000000000000020',recipient_parent_identity='1234abcd:0000000000000021')
    proposal=build_transfer_plan_at_user_profile_v1(data)
    assert proposal['parent_scope']=='UserProfileV1' and proposal['argv'] is None
    assert all(v is False for v in proposal['permissions'].values())
    data['parent_scope']='fallback'
    with pytest.raises(ValueError):build_transfer_plan_at_user_profile_v1(data)
