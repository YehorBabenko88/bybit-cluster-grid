import copy
import pytest
from integration.python_containment_evidence import validate, CASES
HEAD='a'*40

def sample():
    child=dict(schema=1,head=HEAD,run_id='12',attempt='1',pid=123,python_version='3.12 synthetic',status='PASS',error=None,error_code=None,self_loopback=[dict(family=f,stage=s,result='SUCCESS',kind=None,winerror=None,errno=None,wsa_post_exception=None) for f in (4,6) for s in ('socket','connect','accept','exchange')]+[dict(family=4,stage=s,result='SUCCESS',kind=None,winerror=None,errno=None,wsa_post_exception=None) for s in ('stock-socketpair','stock-proactor')],network_isolation=[dict(family=f,status='OBSERVED',api_status=0,missing_capability=1) for f in (4,6)],cases=[dict(name=n,outcome='PASS') for n in CASES],network_diagnostics=[dict(family=f,stage=stage,result='ERROR' if stage in ('accept','connect') else 'SUCCESS',kind='PERMISSION' if stage=='connect' else 'OSERROR' if stage=='accept' else None,winerror=10013 if stage=='connect' else 10035 if stage=='accept' else None,errno=13 if stage=='connect' else 10035 if stage=='accept' else None,wsa_post_exception=0 if stage in ('accept','connect') else None) for f in (4,6) for stage in ('socket','bind','listen','accept','client-socket','connect')]+[dict(family=4,stage='documentation-connect',result='ERROR',kind='PERMISSION',winerror=10013,errno=13,wsa_post_exception=0)],physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False,whole_system='PARTIAL')
    return dict(schema=1,head=HEAD,run_id='12',attempt='1',status='PASS',reason=None,input_manifest_sha256='a'*64,result_sha256='b'*64,diagnostic_sha256='c'*64,diagnostic_error=None,result_error=None,files=15,pid=123,debugged=True,network_host=[dict(family=f,stage=s,success=True) for f in (4,6) for s in ('socket','bind','listen','connect','accept')]+[dict(family=f,stage='no-pending-after-child',success=True) for f in (4,6)],loader_events=[dict(Event=5,Detail='exit:00000000')],python=child,assurance='HOSTED_DEBUGGED_PYTHON_NEGATIVE_BOUNDARY_ONLY',host_verified=False,execute_authorized=False,cleanup_authorized=False,physical='0/10 NOT_RUN',whole_system='PARTIAL',network_transport='BLOCKED_NO_CAPABILITIES')

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


@pytest.mark.parametrize('winerror,errno',[(10022,10022),(10061,10061),(None,13),(True,13),(None,None)])
def test_network_unknown_or_refused_is_not_policy_denial(winerror,errno):
    from integration.windows_python_probe import network_denial
    with pytest.raises(RuntimeError):network_denial(winerror,errno)

def test_network_exact_winsock_access_denied():
    from integration.windows_python_probe import network_denial
    network_denial(10013,13)


def test_timeout_is_explicit_and_not_a_policy_denial():
    from integration.windows_python_probe import socket_error
    row=socket_error(TimeoutError())
    assert row==dict(kind='TIMEOUT',winerror=None,errno=None)
    with pytest.raises(RuntimeError):
        from integration.windows_python_probe import network_denial
        network_denial(row['winerror'],row['errno'])

@pytest.mark.parametrize('error,kind',[(ConnectionRefusedError(10061,'synthetic'),'REFUSED'),(OSError(10022,'synthetic'),'OSERROR'),(PermissionError(13,'synthetic'),'PERMISSION')])
def test_socket_error_kind_is_preserved(error,kind):
    from integration.windows_python_probe import socket_error
    assert socket_error(error)['kind']==kind


@pytest.mark.parametrize('change',['missing-stage','timeout','reorder','unknown-field'])
def test_staged_socket_evidence_cannot_be_truncated_or_promoted(change):
    v=sample();rows=v['python']['network_diagnostics']
    if change=='missing-stage':rows.pop(0)
    elif change=='timeout':rows[5].update(kind='TIMEOUT',winerror=None,errno=None)
    elif change=='reorder':rows.reverse()
    else:rows[0]['unknown']='untrusted'
    with pytest.raises(ValueError):validate(v,HEAD,'12','1')


@pytest.mark.parametrize('status,capability',[(5,1),(None,1),(True,1),(0,4),(0,None)])
def test_unknown_network_isolation_diagnosis_stays_blocked(status,capability):
    from integration.windows_python_probe import isolation_fact
    assert isolation_fact(status,capability)['status']=='BLOCKED'

@pytest.mark.parametrize('capability',[0,1,2,3])
def test_only_documented_netiso_enums_are_observations(capability):
    from integration.windows_python_probe import isolation_fact
    assert isolation_fact(0,capability)['status']=='OBSERVED'


def test_only_complete_successful_self_ipc_controls_are_known():
    from integration.windows_python_probe import self_ipc_proven
    good=[dict(family=f,stage=s,result='SUCCESS',kind=None,winerror=None,errno=None,wsa_post_exception=None) for f in (4,6) for s in ('socket','connect','accept','exchange')]+[dict(family=4,stage=s,result='SUCCESS',kind=None,winerror=None,errno=None,wsa_post_exception=None) for s in ('stock-socketpair','stock-proactor')]
    assert self_ipc_proven(good)
    assert not self_ipc_proven(good[:-1])
    bad=copy.deepcopy(good);bad[1].update(result='ERROR',kind='TIMEOUT')
    assert not self_ipc_proven(bad)


def test_self_ipc_exchange_accepts_segmented_tcp_bytes():
    from integration.windows_python_probe import recv_exact
    class Channel:
        def __init__(self):self.parts=iter([b'o',b'w',b'n'])
        def recv(self,n):return next(self.parts)
    assert recv_exact(Channel(),3)==b'own'

def test_self_ipc_exchange_refuses_early_eof():
    from integration.windows_python_probe import recv_exact
    class Channel:
        def recv(self,n):return b''
    with pytest.raises(RuntimeError):recv_exact(Channel(),3)
