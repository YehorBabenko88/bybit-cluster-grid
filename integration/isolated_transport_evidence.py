"""Read-only consistency checks and BLOCKED diagnostic receipts, never authority."""
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as E
from installer.native_observer_ci import token_facts,valid_sid
from tools.check_ddl_free_ci import ROOT,verify_checkout
from tools.transport_reproducer_bundle import validate_manifest
from integration.windows_transport_probe import validate_config,targets,native_scope
from integration.pipe_probe_protocol import validate_config as pipe_config,validate_frame
from integration.pipe_dacl_evidence import validate_descriptor

def need(ok,code='ISOLATED_TRANSPORT_EVIDENCE_REFUSED'):
    if not ok:raise ValueError(code)

def integer(value,low=0,high=2**63-1):return type(value) is int and low<=value<=high

def load(raw):
    need(type(raw) is bytes and 0<len(raw)<=10000000)
    text=raw.decode('utf-8-sig');depth=0;quoted=False;escaped=False
    for c in text:
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c in '[{':
            depth+=1;need(depth<=24)
        elif c in ']}':depth-=1
    def pairs(items):
        out={}
        for k,v in items:need(k not in out);out[k]=v
        return out
    def number(s):need(len(s)<=80);return int(s)
    return json.loads(text,object_pairs_hook=pairs,parse_int=number,parse_constant=lambda _:need(False))

def validate_header(v,head,run,attempt):
    need(type(v) is dict and type(v.get('schema')) is int and v['schema']==1)
    need((v.get('head'),v.get('run_id'),v.get('attempt'))==(head,run,attempt))
    need(v.get('profile') in ('GRID_FREE_DIAGNOSTIC_ONLY','ONE_WAY_FIXED_PING_PROTOTYPE_ONLY') and type(v.get('debugged')) is bool)
    need(v.get('status')=='BLOCKED' and type(v.get('reason')) is str and re.fullmatch('[A-Za-z0-9_]{1,256}',v['reason']))
    need(v.get('physical')=='0/10 NOT_RUN' and v.get('whole_system')=='PARTIAL')
    for key in ('host_verified','execute_authorized','cleanup_authorized'):need(v.get(key) is False)
    common={'schema','head','run_id','attempt','profile','debugged','status','reason','parent','config','child_identity','input_manifest_sha256','result_sha256','child_exit_code','loader_events','child','host_verified','execute_authorized','cleanup_authorized','physical','whole_system','fixture_teardown'}
    extra={'endpoints','host_controls','accepts','tcp_snapshots','sampler_joined'} if v['profile']=='GRID_FREE_DIAGNOSTIC_ONLY' else {'pipe_ownership','frame_sha256','reader_joined','retained_on_unknown','prototype_result'}
    need(set(v)<=common|extra)

def token(v):
    need(type(v) is dict and set(v)=={'User','Elevated','Integrity','Groups','Fingerprint'})
    need(type(v['Groups']) is list)
    groups=[]
    for g in v['Groups']:
        need(type(g) is dict and set(g)=={'Sid','Attributes'});groups.append(dict(sid=g['Sid'],attributes=g['Attributes']))
    out=dict(user=v['User'],elevated=v['Elevated'],integrity=v['Integrity'],groups=groups,fingerprint=v['Fingerprint']);token_facts(out);return out

def validate_security(parent,child):
    need(type(parent) is dict and set(parent)=={'pid','creation_time','token'})
    need(integer(parent['pid'],1,2**32-1) and integer(parent['creation_time'],1));p=token(parent['token'])
    fields={'pid','creation_time','image','token','is_appcontainer','capability_count','appcontainer_sid','has_restrictions','restriction_creation_flags','job_member','job_flags','job_active_limit'}
    need(type(child) is dict and set(child)==fields and integer(child['pid'],1,2**32-1) and child['pid']!=parent['pid'] and integer(child['creation_time'],parent['creation_time']))
    t=token(child['token']);need(t['user']==p['user'] and t['elevated'] is False and t['integrity']==4096)
    need(all(g['sid']!='S-1-5-32-544' or not(g['attributes']&4) for g in t['groups']))
    for key,value in (('is_appcontainer',1),('capability_count',0),('restriction_creation_flags',5),('job_flags',0x2008),('job_active_limit',1)):
        need(type(child[key]) is int and child[key]==value)
    need(type(child['has_restrictions']) is int and child['has_restrictions'] in (0,1) and child['job_member'] is True)
    need(valid_sid(child['appcontainer_sid']) and re.fullmatch(r'S-1-15-2(?:-[0-9]+){7}',child['appcontainer_sid']))
    need(type(child['image']) is str and len(child['image'])<=2048)
    from pathlib import PureWindowsPath
    image=PureWindowsPath(child['image']);need(image.name=='pythonw.exe');native_scope(str(image.parent),'HOSTED',['--native-child'],'win32',True)

def require_binaries(names):
    need({'NativePythonContainment'+suffix for suffix in ('.exe','.dll','.deps.json','.runtimeconfig.json')}<=set(names),'NATIVE_BINARY_CLOSURE')

def validate_tcp_snapshots(snapshots,parent_pid,child_pid,cfg):
    need(type(snapshots) is list and 2<=len(snapshots)<=60 and snapshots[0]['phase']=='suspended' and snapshots[-1]['phase']=='exited')
    for sample in snapshots:
        tables=sample['tables'];need(tables.get('complete') is True and len(tables['families'])==2)
        for f,expected in zip(tables['families'],(2,23)):
            need(type(f.get('family')) is int and f['family']==expected and type(f.get('raw_api_status')) is int and f['raw_api_status']==0 and f.get('complete') is True and integer(f.get('total_row_count'),0,65536))
            need(type(f.get('rows')) is list and all(integer(r.get('owning_pid'),1) and r['owning_pid'] in (parent_pid,child_pid) and integer(r.get('state'),1,12) for r in f['rows']))
            if sample['phase'] in ('suspended','exited'):
                family='IPv4' if expected==2 else 'IPv6';target=next(t for t in cfg['endpoints'] if t[0]==family and t[3]=='listener')
                need(any(r['owning_pid']==parent_pid and r['state']==2 and r.get('local_address')==target[1] and type(r.get('local_port')) is int and r['local_port']==target[2] for r in f['rows']),'PARENT_LISTENER_NOT_OBSERVED')

def observe(v,head,run,attempt,manifest,driver,frame=None):
    validate_header(v,head,run,attempt);validate_manifest(manifest,head,run,attempt,driver);validate_security(v['parent'],v['child_identity'])
    child=v['child'];need(type(child) is dict and integer(child.get('pid'),1) and child['pid']==v['child_identity']['pid'])
    need((child.get('head'),child.get('run_id'),child.get('attempt'))==(head,run,attempt) and v.get('child_exit_code')==0 and type(v.get('child_exit_code')) is int)
    need(child.get('isolated') is True and child.get('grid_modules_empty') is True)
    cfg=v['config'];need(cfg['parent_pid']==v['parent']['pid'] and child['parent_pid']==cfg['parent_pid'] and child['nonce']==cfg['nonce'])
    if v['profile']=='GRID_FREE_DIAGNOSTIC_ONLY':
        need(set(child)=={'schema','head','run_id','attempt','nonce','parent_pid','pid','python_version','isolated','grid_modules','grid_modules_empty','self_controls','attempts','status','physical_status','physical_ready','host_verified','verified_safety_cases','execution_authorized','cleanup_authorized','readiness_passed','automatic_resume'})
        validate_config(cfg);need(child.get('status')=='OBSERVED_NOT_ATTESTED' and child.get('grid_modules')==[] and v.get('sampler_joined') is True)
        for name in ('physical_ready','host_verified','readiness_passed','execution_authorized','cleanup_authorized','automatic_resume'):need(child.get(name) is False)
        need(type(child.get('verified_safety_cases')) is int and child['verified_safety_cases']==0 and child.get('physical_status')=='0/10 NOT_RUN')
        controls=child.get('self_controls');need(type(controls) is list and [r.get('name') for r in controls]==['IPv4','IPv6','socketpair'] and all(r.get('complete') is True and r.get('evidence')=='UNKNOWN' and r.get('error') is None for r in controls))
        endpoints=targets(cfg);attempts=child.get('attempts');need(type(attempts) is list and len(attempts)==6)
        for row,target in zip(attempts,endpoints):
            fields={'family','host','port','mode','started_utc_ms','deadline_ms','elapsed_ms','initial_code','so_error','poll_trace','peer_endpoint','local_endpoint','local_error','error','stage','connected','classification','evidence','complete','bind_policy'}
            need(type(row) is dict and fields<=set(row) and set(row)<=fields|{'close_error'} and row.get('close_error') is None)
            need(type(row) is dict and tuple(row.get(k) for k in ('family','host','port','mode'))==target and row.get('evidence')=='UNKNOWN' and row.get('complete') is True and type(row.get('connected')) is bool)
            need(row.get('bind_policy')=='IMPLICIT_OS_SELECTED' and type(row.get('deadline_ms')) is int and row['deadline_ms']==6000 and integer(row.get('elapsed_ms'),0,11000))
            need(row.get('classification') in ('ERROR10013','ERROR10061','OTHER_ERROR','TIMEOUT','UNEXPECTED_CONNECTION','PEER_MISMATCH'))
            for key in ('initial_code','so_error'):need(row.get(key) is None or integer(row[key],0,2**32-1))
            trace=row.get('poll_trace');need(type(trace) is list and len(trace)<=80)
            for p in trace:need(type(p) is dict and set(p)=={'elapsed_ms','readable','writable','exceptional'} and integer(p['elapsed_ms'],0,11000) and all(type(p[k]) is bool for k in ('readable','writable','exceptional')))
            if row['so_error'] is not None:need(len(trace)>0 and any(trace[-1][k] for k in ('readable','writable','exceptional')) and row['initial_code'] in (10035,10036,10037))
            code=row['so_error'] if row['so_error'] is not None else row['initial_code']
            if row['classification'] in ('ERROR10013','ERROR10061'):need(code==int(row['classification'][5:]))
            if row['classification']=='OTHER_ERROR':need(type(code) is int and code not in (0,10013,10061,10035,10036,10037))
            if row['classification']=='TIMEOUT':need(row['elapsed_ms']>=5900 and row['so_error'] is None and row['initial_code'] in (10035,10036,10037) and not any(p[k] for p in trace for k in ('readable','writable','exceptional')))
            if row['connected']:need(row.get('peer_endpoint') is not None and row['peer_endpoint'][:2]==[target[1],target[2]] and row['classification']=='UNEXPECTED_CONNECTION')
        host=v['host_controls'];need(type(host) is list and len(host)==8)
        for row,(phase,target) in zip(host,[(phase,target) for phase in ('before','after') for target in endpoints[:4]]):
            family,address,port,mode=target;need((row.get('phase'),row.get('family'),row.get('mode'))==(phase,family,mode) and row.get('target')==dict(host=address,port=port))
            need((row.get('result'),row.get('winerror'))==('SUCCESS',None) if mode=='listener' else row.get('result')=='SOCKET_ERROR' and type(row.get('winerror')) is int and row['winerror']==10061)
        accepts=v['accepts'];need(type(accepts) is list and [r['family'] for r in accepts]==['IPv4','IPv6'] and all(r['status'] in ('CANCELLED_NO_ACCEPT','ACCEPTED_NOT_AUTHENTICATED') for r in accepts))
        validate_tcp_snapshots(v['tcp_snapshots'],v['parent']['pid'],child['pid'],cfg)
        return dict(kind='GRID_FREE_SOCKET_OBSERVATIONS',policy_cause='UNKNOWN',attempts=[dict(family=r['family'],mode=r['mode'],classification=r['classification'],initial_code=r['initial_code'],so_error=r['so_error']) for r in attempts])
    pipe_config(cfg);need(v.get('prototype_result')=='FIXED_PING_OBSERVED' and child.get('status')=='PARTIAL_NO_GRID_AUTHORITY' and v.get('reader_joined') is True and v.get('retained_on_unknown') is False)
    for name in ('owner_authenticated','process_lifetime_authenticated','physical_ready','host_verified','execution_authorized','cleanup_authorized','readiness_passed','automatic_resume'):need(child.get(name) is False)
    need(set(child)=={'schema','head','run_id','attempt','nonce','parent_pid','pid','status','isolated','grid_modules_empty','denials','frame_written_bytes','frame_sha256','frame_write_winerror','owner_authenticated','process_lifetime_authenticated','physical','physical_ready','host_verified','execution_authorized','cleanup_authorized','readiness_passed','verified_safety_cases','automatic_resume'})
    need(child.get('physical')=='0/10 NOT_RUN' and type(child.get('verified_safety_cases')) is int and child['verified_safety_cases']==0 and child.get('frame_write_winerror') is None)
    need(child.get('denials')=={k:dict(opened=False,winerror=5,status='OBSERVED') for k in ('pipe_read','parent_process_read','foreign_canary_read')})
    for d in child['denials'].values():need(d['opened'] is False and type(d['winerror']) is int)
    expected={k:cfg[k] for k in ('head','run_id','attempt','nonce')};expected['pid']=child['pid'];validate_frame(frame,expected);digest=hashlib.sha256(frame).hexdigest()
    need(child['frame_sha256']==v['frame_sha256']==digest and type(child.get('frame_written_bytes')) is int and child['frame_written_bytes']==len(frame))
    p=v['pipe_ownership'];need(p.get('parent_writer_closed') is True and p.get('read_handle_inheritable') is False and p.get('write_handle_inheritable_before_drop') is True and type(p.get('package_dacl_grant_mask')) is int and p['package_dacl_grant_mask']==0x120116 and type(p.get('dacl_ace_count')) is int and p['dacl_ace_count']==3)
    need(p.get('granted_access')=='NOT_INDEPENDENTLY_QUERIED' and p.get('label')=='LABEL_UNVERIFIED' and p.get('assurance')=='OBSERVED_NOT_ATTESTED')
    validate_descriptor(p.get('descriptor_base64'),v['parent']['token']['User'],v['child_identity']['appcontainer_sid'])
    for name in ('host_verified','execute_authorized','cleanup_authorized'):need(p.get(name) is False)
    return dict(kind='FIXED_PING_AND_THREE_DENIALS_OBSERVED',policy_cause='UNKNOWN',owner_authenticated=False,grid_adapter_proven=False)

def sources(head):
    paths=['installer/native-python-containment','installer/native-g1-controller-fixture','installer/native-acl-observer','installer/native-acl-transaction-fixture','tools/transport_reproducer_bundle.py','tools/python_containment_bundle.py','integration/windows_transport_probe.py','integration/windows_pipe_probe.py','integration/pipe_probe_protocol.py','integration/pipe_dacl_evidence.py','integration/isolated_transport_evidence.py','.github/workflows/windows-python-containment.yml']
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',head,*paths],cwd=ROOT,text=True).splitlines()
    return {n:hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest() for n in names}

def create(folder,head,run,attempt):
    folder=Path(folder).resolve();need(folder.parent==ROOT and folder.name in ('transport-debugged-evidence','transport-undebugged-evidence','pipe-debugged-evidence','pipe-undebugged-evidence'))
    verify_checkout(ROOT,head)
    def raw(name):
        path=folder/name;st=path.lstat();need(path.is_file() and not path.is_symlink() and st.st_nlink==1 and not getattr(st,'st_file_attributes',0)&0x400 and st.st_size<=10000000);return path.read_bytes()
    v=load(raw('native.json'));validate_header(v,head,run,attempt);m=load(raw('input.json'));driver_path='integration/windows_pipe_probe.py' if folder.name.startswith('pipe-') else 'integration/windows_transport_probe.py'
    detail=None;validation='OBSERVATION_INCOMPLETE'
    try:
        child=raw('child.json');need(load(child)==v['child'] and hashlib.sha256(child).hexdigest()==v['result_sha256'] and hashlib.sha256(raw('input.json')).hexdigest()==v['input_manifest_sha256'])
        driver=subprocess.check_output(['git','show',head+':'+driver_path],cwd=ROOT);detail=observe(v,head,run,attempt,m,driver,raw('frame.bin') if folder.name.startswith('pipe-') else None);validation='STRUCTURALLY_CONSISTENT_NOT_ATTESTED'
    except (ValueError,TypeError,KeyError,OSError,IndexError):pass
    summary=dict(schema=1,head=head,run_id=run,attempt=attempt,profile=v['profile'],debugged=v['debugged'],status='BLOCKED',validation=validation,observations=detail,policy_cause='UNKNOWN',provenance_authenticated=False,owner_authenticated=False,host_verified=False,execute_authorized=False,cleanup_authorized=False,physical='0/10 NOT_RUN',whole_system='PARTIAL')
    with (folder/'observation.json').open('x',encoding='utf8') as f:f.write(json.dumps(summary,sort_keys=True))
    with (folder/'events.jsonl').open('x',encoding='utf8') as f:f.write(json.dumps(summary,sort_keys=True)+'\n')
    xml=E.Element('testsuite',head=head,run_id=run,attempt=attempt,tests='1',failures='1',errors='0',skipped='0');case=E.SubElement(xml,'testcase',classname='unaccepted_transport_diagnostic',name=folder.name);E.SubElement(case,'failure',message='POLICY_OR_FULL_TRANSPORT_UNPROVEN').text=validation
    with (folder/'junit.xml').open('xb') as f:E.ElementTree(xml).write(f,encoding='utf-8',xml_declaration=True)
    allowed={'native.json','child.json','input.json','diagnostics.txt','transport-host.json','frame.bin','observation.json','events.jsonl','junit.xml','NativePythonContainment.exe','NativePythonContainment.dll','NativePythonContainment.deps.json','NativePythonContainment.runtimeconfig.json'}
    names={p.name for p in folder.iterdir()};require_binaries(names);need(names<=allowed and {'native.json','input.json','observation.json','events.jsonl','junit.xml'}<=names)
    index=dict(head=head,run_id=run,attempt=attempt,files={n:hashlib.sha256(raw(n)).hexdigest() for n in sorted(names)},sources=sources(head),status='BLOCKED',physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False)
    with (folder/'sha256.json').open('x',encoding='utf8') as f:f.write(json.dumps(index,sort_keys=True))
    verify_checkout(ROOT,head);return summary

if __name__=='__main__':
    summary=create(sys.argv[1],os.environ['EXACT_HEAD_SHA'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT']);print(json.dumps(summary));raise SystemExit(0 if summary['validation']=='STRUCTURALLY_CONSISTENT_NOT_ATTESTED' else 1)
