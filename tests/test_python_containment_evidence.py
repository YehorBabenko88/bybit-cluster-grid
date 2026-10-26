import copy
import pytest
from integration.python_containment_evidence import validate, CASES
HEAD='a'*40

def sample():
    child=dict(schema=1,head=HEAD,run_id='12',attempt='1',pid=123,python_version='3.12 synthetic',status='PASS',error=None,error_code=None,cases=[dict(name=n,outcome='PASS') for n in CASES],physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False,whole_system='PARTIAL')
    return dict(schema=1,head=HEAD,run_id='12',attempt='1',status='PASS',reason=None,input_manifest_sha256='a'*64,result_sha256='b'*64,diagnostic_sha256='c'*64,diagnostic_error=None,result_error=None,files=15,pid=123,debugged=True,loader_events=[dict(Event=5,Detail='exit:00000000')],python=child,assurance='HOSTED_DEBUGGED_PYTHON_NEGATIVE_BOUNDARY_ONLY',host_verified=False,execute_authorized=False,cleanup_authorized=False,physical='0/10 NOT_RUN',whole_system='PARTIAL',network_transport='BLOCKED_NO_CAPABILITIES')

def test_exact_negative_boundary_only():validate(sample(),HEAD,'12','1')
@pytest.mark.parametrize('field,value',[('head','f'*40),('run_id','13'),('pid',True),('status','BLOCKED'),('whole_system','PASS'),('host_verified',True),('execute_authorized',True),('extra','unknown')])
def test_parent_claim_tamper(field,value):
    v=sample();v[field]=value
    with pytest.raises(ValueError):validate(v,HEAD,'12','1')
@pytest.mark.parametrize('field,value',[('pid',124),('head','f'*40),('physical','10/10 PASS'),('cleanup_authorized',True),('extra','unknown')])
def test_child_claim_tamper(field,value):
    v=sample();v['python'][field]=value
    with pytest.raises(ValueError):validate(v,HEAD,'12','1')
@pytest.mark.parametrize('kind',['missing','reordered','failed','duplicate'])
def test_real_component_case_inventory(kind):
    v=sample();rows=v['python']['cases']
    if kind=='missing':rows.pop()
    elif kind=='reordered':rows.reverse()
    elif kind=='failed':rows[-1]['outcome']='FAIL'
    else:rows[-1]=copy.deepcopy(rows[0])
    with pytest.raises(ValueError):validate(v,HEAD,'12','1')


@pytest.mark.parametrize('mutation',['relabel-driver','relabel-grid','missing-grid','extra-grid','changed-grid','unknown-origin'])
def test_input_git_origin_is_not_self_selected(mutation):
    from integration.python_containment_evidence import input_policy
    pins={'driver.py':'A'*64,'Source/grid/worker.py':'B'*64}
    m={'Files':{n:{'Sha256':h,'Length':1} for n,h in pins.items()},'Origins':{n:'git:'+HEAD for n in pins}}
    if mutation=='relabel-driver':m['Origins']['driver.py']='pinned-requirements-resolved'
    elif mutation=='relabel-grid':m['Origins']['Source/grid/worker.py']='setup-python'
    elif mutation=='missing-grid':m['Files'].pop('Source/grid/worker.py');m['Origins'].pop('Source/grid/worker.py')
    elif mutation=='extra-grid':m['Files']['Source/grid/evil.py']={'Sha256':'C'*64,'Length':1};m['Origins']['Source/grid/evil.py']='git:'+HEAD
    elif mutation=='changed-grid':m['Files']['Source/grid/worker.py']['Sha256']='C'*64
    else:m['Files']['Site/evil.py']={'Sha256':'C'*64,'Length':1};m['Origins']['Site/evil.py']='untrusted'
    with pytest.raises(ValueError):input_policy(m,HEAD,pins)


@pytest.mark.parametrize('host,args,root',[
 ('LS5',['--native-child'],r'C:\Lab\Packages\g1-fixture-00000000-0000-4000-8000-000000000001\AC\python-00000000-0000-4000-8000-000000000002'),
 ('PC4',['--native-child'],r'C:\Lab\Packages\g1-fixture-00000000-0000-4000-8000-000000000001\AC\python-00000000-0000-4000-8000-000000000002'),
 ('runner',[],r'C:\Lab\Packages\g1-fixture-00000000-0000-4000-8000-000000000001\AC\python-00000000-0000-4000-8000-000000000002'),
 ('runner',['--native-child'],r'C:\GridLab'),
 ('runner',['--native-child'],r'C:\Lab\Packages\foreign\AC\python-00000000-0000-4000-8000-000000000002'),
], ids=['ls5','pc4','missing-argument','foreign-root','foreign-package'])
def test_driver_refuses_physical_or_unowned_scope(host,args,root):
    from integration.windows_python_probe import native_scope
    with pytest.raises(ValueError):native_scope(root,host,args)


def test_driver_accepts_only_fresh_guid_profile_shape_in_model():
    from integration.windows_python_probe import native_scope
    native_scope(r'C:\Lab\Packages\g1-fixture-00000000-0000-4000-8000-000000000001\AC\python-00000000-0000-4000-8000-000000000002','runner',['--native-child'])


@pytest.mark.parametrize('opened,error',[(True,0),(False,32),(False,13),(False,None),(False,True)])
def test_crt_or_sharing_errors_are_not_acl_denial(opened,error):
    from integration.windows_python_probe import win32_denial
    with pytest.raises(RuntimeError):win32_denial(opened,error)

def test_exact_win32_access_denied_is_required():
    from integration.windows_python_probe import win32_denial
    win32_denial(False,5)


@pytest.mark.parametrize('error',[5,32,None,True,0,0x1C0000008])
def test_unknown_foreign_handle_failure_is_not_absence(error):
    from integration.windows_python_probe import unavailable_handle
    with pytest.raises(RuntimeError):unavailable_handle(error)

@pytest.mark.parametrize('error',[6,-1073741816,0xC0000008])
def test_exact_invalid_handle_status_proves_absence(error):
    from integration.windows_python_probe import unavailable_handle
    unavailable_handle(error)


def test_file_identity_matches_native_high_low_format_not_memory_hex():
    from integration.windows_python_probe import file_identity
    volume,low,high=7,0x0102030405060708,0x1020304050607080
    raw=volume.to_bytes(8,'little')+low.to_bytes(8,'little')+high.to_bytes(8,'little')
    assert file_identity(raw)==(volume,'10203040506070800102030405060708')
    assert raw[8:].hex().upper()!='10203040506070800102030405060708'

@pytest.mark.parametrize('raw',[b'',b'0'*23,b'0'*25])
def test_file_identity_refuses_partial_structures(raw):
    from integration.windows_python_probe import file_identity
    with pytest.raises(RuntimeError):file_identity(raw)
