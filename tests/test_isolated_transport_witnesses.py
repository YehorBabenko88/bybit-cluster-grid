"""Independent offline witnesses; no sockets, native calls, or bundle builds."""
import hashlib
import json
import struct,base64

import pytest

from integration import isolated_transport_evidence as evidence

HEAD, RUN, ATTEMPT, NONCE = 'a'*40, '12', '1', 'b'*32
DRIVER = b'# exact synthetic measured Git driver\n'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def token(elevated=False, level=4096):
    user = 'S-1-5-21-1-2-3-1001'
    groups = [dict(Sid='S-1-5-32-545', Attributes=7), dict(Sid='S-1-5-32-544', Attributes=16)]
    raw = dict(user=user, elevated=elevated, level=level, groups=groups)
    return dict(User=user, Elevated=elevated, Integrity=level, Groups=groups,
                Fingerprint=digest(json.dumps(raw, separators=(',', ':')).encode()).upper())


def manifest():
    files = {'python.exe': b'exe', 'pythonw.exe': b'gui', 'python312.dll': b'dll',
             'DLLs/_socket.pyd': b'pyd', 'DLLs/_ctypes.pyd': b'ctypes',
             'DLLs/_ssl.pyd': b'ssl', 'stdlib.zip': b'zip', 'driver.py': DRIVER,
             'python._pth': b'stdlib.zip\nDLLs\n', 'pythonw._pth': b'stdlib.zip\nDLLs\n',
             'python312._pth': b'stdlib.zip\nDLLs\n'}
    return dict(Schema=1, Head=HEAD, Run=RUN, Attempt=ATTEMPT, Python='3.12',
        Files={n: dict(Sha256=digest(b).upper(), Length=len(b)) for n, b in files.items()},
        Origins={n: 'git:'+HEAD if n=='driver.py' else 'fixed-isolated-paths' if n.endswith('._pth') else 'setup-python-stdlib' if n=='stdlib.zip' else 'setup-python' for n in files})


def base(pipe=False):
    return dict(schema=1, head=HEAD, run_id=RUN, attempt=ATTEMPT,
        profile='ONE_WAY_FIXED_PING_PROTOTYPE_ONLY' if pipe else 'GRID_FREE_DIAGNOSTIC_ONLY',
        debugged=False, status='BLOCKED', reason='POLICY_CAUSE_UNKNOWN',
        parent=dict(pid=10, creation_time=100, token=token(True, 12288)),
        child_identity=dict(pid=20, creation_time=101,
            image='C:/Users/runner/AppData/Local/Packages/g1-fixture-11111111-1111-4111-8111-111111111111/AC/python-22222222-2222-4222-8222-222222222222/pythonw.exe',
            token=token(), is_appcontainer=1, capability_count=0, appcontainer_sid='S-1-15-2-1-2-3-4-5-6-7',
            has_restrictions=None,restriction_observation=dict(information_class=21,returned_length=1,raw_hex="01",status="RAW_ONLY_NOT_SECURITY_ASSERTION"), restriction_creation_flags=5, job_member=True, job_flags=0x2008, job_active_limit=1),
        input_manifest_sha256='c'*64, result_sha256='d'*64, child_exit_code=0, loader_events=[],
        host_verified=False, execute_authorized=False, cleanup_authorized=False,
        physical='0/10 NOT_RUN', whole_system='PARTIAL', fixture_teardown='DISPOSABLE_VM_TEARDOWN_REQUIRED')


def child_base():
    return dict(schema=1, head=HEAD, run_id=RUN, attempt=ATTEMPT, nonce=NONCE,
                pid=20, parent_pid=10, isolated=True, grid_modules_empty=True,
                physical_ready=False, host_verified=False, readiness_passed=False,
                execution_authorized=False, cleanup_authorized=False,
                automatic_resume=False, verified_safety_cases=0)


def tcp_witness():
    v=base(); endpoints=[['IPv4','127.0.0.1',40001,'listener'], ['IPv4','127.0.0.1',40002,'bound-not-listening'],
                         ['IPv6','::1',40003,'listener'], ['IPv6','::1',40004,'bound-not-listening']]
    v['config']=dict(schema=1,head=HEAD,run_id=RUN,attempt=ATTEMPT,nonce=NONCE,parent_pid=10,endpoints=endpoints)
    child=child_base(); child.update(python_version='3.12.0', grid_modules=[], status='OBSERVED_NOT_ATTESTED', physical_status='0/10 NOT_RUN',
        self_controls=[dict(name=n,complete=True,evidence='UNKNOWN',error=None) for n in ('IPv4','IPv6','socketpair')])
    child['attempts']=[]
    for family, host, port, mode in endpoints+[['IPv4','192.0.2.1',9,'external'],['IPv6','2001:db8::1',9,'external']]:
        child['attempts'].append(dict(family=family,host=host,port=port,mode=mode,
            started_utc_ms=1000,deadline_ms=6000,elapsed_ms=1,initial_code=10013,so_error=None,poll_trace=[],
            peer_endpoint=None,local_endpoint=['0.0.0.0' if family=='IPv4' else '::',0],local_error=None,
            error=None,stage='connect_ex',connected=False,classification='ERROR10013',evidence='UNKNOWN',complete=True,bind_policy='IMPLICIT_OS_SELECTED'))
    v['child']=child; v['sampler_joined']=True
    v['endpoints']=[dict(family=f,host=h,port=p,mode=m,backlog=4 if m=='listener' else 0,exclusive=True,dual_mode=False,ready_utc_ms=900,ready_monotonic=10) for f,h,p,m in endpoints]
    v['host_controls']=[dict(phase=phase,family=f,mode=m,target=dict(host=h,port=p),
        result='SUCCESS' if m=='listener' else 'SOCKET_ERROR',winerror=None if m=='listener' else 10061,
        started_utc_ms=900,elapsed_ms=1) for phase in ('before','after') for f,h,p,m in endpoints]
    v['accepts']=[dict(family=f,status='CANCELLED_NO_ACCEPT') for f in ('IPv4','IPv6')]
    v['tcp_snapshots']=[]
    for phase in ('suspended','exited'):
        families=[]
        for af,host,port in ((2,'127.0.0.1',40001),(23,'::1',40003)):
            families.append(dict(family=af,raw_api_status=0,complete=True,total_row_count=1,reason=None,excluded_owned_rows=0,
                rows=[dict(local_address=host,local_port=port,remote_address=None,remote_port=None,state=2,owning_pid=10)]))
        v['tcp_snapshots'].append(dict(phase=phase,utc_ms=1000,monotonic=20,tables=dict(complete=True,reason='OBSERVED_NOT_ATTESTED',families=families)))
    return v


def pipe_descriptor():
    def sid(text):
        p=[int(x) for x in text.split('-')[1:]]
        return bytes([1,len(p)-2])+p[1].to_bytes(6,'big')+b''.join(struct.pack('<I',x) for x in p[2:])
    user='S-1-5-21-1-2-3-1001';app='S-1-15-2-1-2-3-4-5-6-7';u=sid(user)
    aces=[]
    for name,mask in [('S-1-5-18',0x1f01ff),(user,0x1f01ff),(app,0x120116)]:
        value=sid(name);aces.append(struct.pack('<BBHI',0,0,8+len(value),mask)+value)
    acl=struct.pack('<BBHHH',2,0,8+sum(map(len,aces)),3,0)+b''.join(aces)
    raw=struct.pack('<BBHIIII',1,0,0x9004,20,20+len(u),0,20+2*len(u))+u+u+acl
    return base64.b64encode(raw).decode('ascii')


def pipe_witness():
    v=base(True); v['config']=dict(schema=1,head=HEAD,run_id=RUN,attempt=ATTEMPT,nonce=NONCE,parent_pid=10,canary='C:/owned/outside.fixture')
    payload=json.dumps(dict(schema=1,verb='ping',head=HEAD,run_id=RUN,attempt=ATTEMPT,nonce=NONCE,pid=20),sort_keys=True,separators=(',',':')).encode('ascii')
    frame=len(payload).to_bytes(4,'little')+payload
    child=child_base(); child.update(status='PARTIAL_NO_GRID_AUTHORITY',physical='0/10 NOT_RUN',owner_authenticated=False,process_lifetime_authenticated=False,
        denials={n:dict(opened=False,winerror=5,status='OBSERVED') for n in ('pipe_read','parent_process_read','foreign_canary_read')},
        frame_written_bytes=len(frame),frame_sha256=digest(frame),frame_write_winerror=None)
    v.update(child=child,prototype_result='FIXED_PING_OBSERVED',reader_joined=True,retained_on_unknown=False,frame_sha256=digest(frame),
        pipe_ownership=dict(schema=1,descriptor_base64=pipe_descriptor(),creation_descriptor_base64='AA==',dacl_ace_count=3,package_dacl_grant_mask=0x120116,
            granted_access='NOT_INDEPENDENTLY_QUERIED',read_handle_inheritable=False,write_handle_inheritable_before_drop=True,parent_writer_closed=True,
            label='LABEL_UNVERIFIED',retained_on_unknown=False,assurance='OBSERVED_NOT_ATTESTED',host_verified=False,execute_authorized=False,cleanup_authorized=False))
    return v,frame


def observe(v, frame=None):
    return evidence.observe(v,HEAD,RUN,ATTEMPT,manifest(),DRIVER,frame)


def test_positive_tcp_witness_is_only_unknown_policy_observation():
    assert observe(tcp_witness())['policy_cause']=='UNKNOWN'


def test_positive_pipe_witness_is_only_fixed_ping_observation():
    v,frame=pipe_witness()
    assert observe(v,frame)['owner_authenticated'] is False


@pytest.mark.parametrize('mutation', ['owner_true','no_listeners','other_zero','terminal_timeout','unknown_root'])
def test_malformed_tcp_witness_rejected(mutation):
    v=tcp_witness()
    if mutation=='owner_true': v['child']['owner_authenticated']=True
    elif mutation=='no_listeners':
        for sample in v['tcp_snapshots']:
            for family in sample['tables']['families']: family['rows']=[]
    elif mutation=='other_zero': v['child']['attempts'][0].update(classification='OTHER_ERROR',initial_code=0)
    elif mutation=='terminal_timeout': v['child']['attempts'][0].update(classification='TIMEOUT',initial_code=10013,elapsed_ms=6000)
    else: v['unknown_authority']=True
    with pytest.raises(ValueError): observe(v)


@pytest.mark.parametrize('mutation', ['frame','denial','owner','descriptor'])
def test_malformed_pipe_witness_rejected(mutation):
    v,frame=pipe_witness()
    if mutation=='frame': frame=frame[:-1]+b'!'
    elif mutation=='denial': v['child']['denials']['pipe_read']['winerror']=10061
    elif mutation=='descriptor':v['pipe_ownership']['descriptor_base64']='AA=='
    else: v['child']['owner_authenticated']=True
    with pytest.raises(ValueError): observe(v,frame)


def test_native_binary_closure_is_required():
    binaries={'NativePythonContainment.exe','NativePythonContainment.dll','NativePythonContainment.deps.json','NativePythonContainment.runtimeconfig.json'}
    evidence.require_binaries(binaries|{'native.json'})
    for missing in binaries:
        with pytest.raises(ValueError): evidence.require_binaries(binaries-{missing})
