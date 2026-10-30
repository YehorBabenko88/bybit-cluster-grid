import copy,hashlib,json
import pytest
from integration.isolated_transport_evidence import validate_header,validate_security

HEAD='a'*40

def token(elevated=False,level=4096):
    user='S-1-5-21-1-2-3-1001';groups=[dict(Sid='S-1-5-32-545',Attributes=7),dict(Sid='S-1-5-32-544',Attributes=16)]
    raw=dict(user=user,elevated=elevated,level=level,groups=groups)
    return dict(User=user,Elevated=elevated,Integrity=level,Groups=groups,Fingerprint=hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest().upper())

def identity():
    return dict(pid=20,creation_time=101,image='C:/Users/runner/AppData/Local/Packages/g1-fixture-11111111-1111-4111-8111-111111111111/AC/python-22222222-2222-4222-8222-222222222222/pythonw.exe',token=token(),is_appcontainer=1,capability_count=0,appcontainer_sid='S-1-15-2-1-2-3-4-5-6-7',has_restrictions=None,restriction_observation=dict(information_class=21,returned_length=1,raw_hex="01",status="RAW_ONLY_NOT_SECURITY_ASSERTION"),restriction_creation_flags=5,job_member=True,job_flags=0x2008,job_active_limit=1)

def test_held_process_token_snapshot_is_observation_only():
    parent=dict(pid=10,creation_time=100,token=token(True,12288))
    validate_security(parent,identity())

@pytest.mark.parametrize('field,value',[('pid',True),('creation_time',99),('is_appcontainer',True),('capability_count',1),('has_restrictions',True),('restriction_creation_flags',0),('job_member',False),('job_flags',0),('job_active_limit',2),('appcontainer_sid','S-1-5-18'),('image','C:/Windows/pythonw.exe')])
def test_unknown_or_changed_security_facts_cannot_validate(field,value):
    v=identity();v[field]=value
    with pytest.raises(ValueError):validate_security(dict(pid=10,creation_time=100,token=token(True,12288)),v)

def test_child_elevation_is_rejected_even_with_consistent_fingerprint():
    v=identity();v['token']=token(True)
    with pytest.raises(ValueError):validate_security(dict(pid=10,creation_time=100,token=token(True,12288)),v)

def header():
    return dict(schema=1,head=HEAD,run_id='12',attempt='1',profile='GRID_FREE_DIAGNOSTIC_ONLY',debugged=True,status='BLOCKED',reason='POLICY_CAUSE_UNKNOWN',host_verified=False,execute_authorized=False,cleanup_authorized=False,physical='0/10 NOT_RUN',whole_system='PARTIAL')

def test_header_never_accepts_pass_or_physical_authority():
    validate_header(header(),HEAD,'12','1')
    for key,value in [('status','PASS'),('head','f'*40),('run_id','13'),('schema',True),('debugged','false'),('host_verified',True),('execute_authorized',True),('cleanup_authorized',True),('physical','10/10 PASS'),('whole_system','PASS'),('authorization',True)]:
        v=header();v[key]=value
        with pytest.raises(ValueError):validate_header(v,HEAD,'12','1')


@pytest.mark.parametrize('size,raw',[(1,'01'),(1,'00'),(4,'01000000'),(4,'00000000')])
def test_class21_raw_payload_does_not_establish_restriction_state(size,raw):
    v=identity();v['restriction_observation'].update(returned_length=size,raw_hex=raw)
    validate_security(dict(pid=10,creation_time=100,token=token(True,12288)),v)
    assert v['has_restrictions'] is None

@pytest.mark.parametrize('field,value',[
 ('information_class',True),('information_class',20),('returned_length',True),
 ('returned_length',2),('returned_length',65536),('raw_hex',''),('raw_hex','GG'),
 ('raw_hex','0100'),('status','PASS')])
def test_invalid_class21_raw_observation_refused(field,value):
    v=identity();v['restriction_observation'][field]=value
    with pytest.raises(ValueError):validate_security(dict(pid=10,creation_time=100,token=token(True,12288)),v)
