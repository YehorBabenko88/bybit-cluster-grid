"""Strict hosted Python-boundary receipt. No physical authority or runtime transport proof."""
import hashlib,json,re,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as E
from .windows_python_probe import CASES
ROOT=Path(__file__).resolve().parents[1]
FIELDS={'schema','head','run_id','attempt','status','reason','input_manifest_sha256','result_sha256','diagnostic_sha256','diagnostic_error','result_error','files','pid','debugged','loader_events','python','assurance','host_verified','execute_authorized','cleanup_authorized','physical','whole_system','network_transport','network_host'}
CHILD={'schema','head','run_id','attempt','pid','python_version','status','error','error_code','cases','physical','execute_authorized','cleanup_authorized','whole_system','network_diagnostics','network_isolation'}

def need(ok):
    if not ok:raise ValueError('PYTHON_BOUNDARY_EVIDENCE_REFUSED')
def load(raw):
    def pairs(items):
        out={}
        for k,v in items:
            need(k not in out);out[k]=v
        return out
    need(len(raw)<10000000)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda s:need(False))
def validate(v,head,run,attempt):
    need(type(v) is dict and set(v)==FIELDS)
    for obj in (v,v['python']):
        need(type(obj) is dict and type(obj.get('schema')) is int and obj['schema']==1)
        need((obj.get('head'),obj.get('run_id'),obj.get('attempt'))==(head,run,attempt))
        need(obj.get('status')=='PASS' and obj.get('physical')=='0/10 NOT_RUN' and obj.get('whole_system')=='PARTIAL')
        need(obj.get('execute_authorized') is False and obj.get('cleanup_authorized') is False)
        need(type(obj.get('pid')) is int and obj['pid']>0)
    need(set(v['python'])==CHILD and v['python']['pid']==v['pid'] and type(v['files']) is int and 10<v['files']<=20000)
    need(v['python']['error'] is None and v['python']['error_code'] is None and v['reason'] is None and v['diagnostic_error'] is None and v['result_error'] is None and v['host_verified'] is False)
    need(type(v['python']['python_version']) is str and v['python']['python_version'].startswith(('3.11','3.12')))
    need(v['assurance']=='HOSTED_DEBUGGED_PYTHON_NEGATIVE_BOUNDARY_ONLY' and v['debugged'] is True and v['network_transport']=='BLOCKED_NO_CAPABILITIES')
    need(type(v['loader_events']) is list and 0<len(v['loader_events'])<=1024 and v['loader_events'][-1]==dict(Event=5,Detail='exit:00000000'))
    for row in v['loader_events']:need(type(row) is dict and set(row)=={'Event','Detail'} and type(row['Event']) is int and row['Event'] in (1,3,5,6,8) and type(row['Detail']) is str and len(row['Detail'])<=8192)
    need(v['network_host']==[dict(family=f,stage=s,success=True) for f in (4,6) for s in ('socket','bind','listen','connect','accept')]+[dict(family=f,stage='no-pending-after-child',success=True) for f in (4,6)])
    isolation=v['python']['network_isolation'];need(type(isolation) is list and len(isolation)==2)
    for family,row in zip((4,6),isolation):need(type(row) is dict and set(row)=={'family','status','api_status','missing_capability'} and type(row['family']) is int and row['family']==family and row['status']=='OBSERVED' and type(row['api_status']) is int and row['api_status']==0 and type(row['missing_capability']) is int and row['missing_capability'] in (0,1,2,3))
    trace=v['python']['network_diagnostics'];need(type(trace) is list and 2<=len(trace)<=32)
    for row in trace:
        need(type(row) is dict and set(row)=={'family','stage','result','kind','winerror','errno','wsa_post_exception'} and type(row['family']) is int and row['family'] in (4,6) and row['stage'] in ('socket','bind','listen','accept','client-socket','connect','documentation-connect') and row['result'] in ('SUCCESS','ERROR'))
        need(row['kind'] in (None,'TIMEOUT','REFUSED','PERMISSION','OSERROR'))
        for k in ('winerror','errno','wsa_post_exception'):need(row[k] is None or type(row[k]) is int and -(2**31)<=row[k]<2**32)
    need([(r['family'],r['stage']) for r in trace]==[(f,s) for f in (4,6) for s in ('socket','bind','listen','accept','client-socket','connect')]+[(4,'documentation-connect')])
    for row in trace:
        if row['result']=='SUCCESS':need(all(row[k] is None for k in ('kind','winerror','errno','wsa_post_exception')))
        else:need(row['kind'] is not None)
    for family in (4,6):
        matches=[r for r in trace if r['family']==family and r['stage']=='connect'];need(len(matches)==1 and matches[0]['result']=='ERROR' and matches[0]['winerror']==10013 and matches[0]['kind']!='TIMEOUT')
    need(trace[-1]['result']=='ERROR' and trace[-1]['winerror']==10013 and trace[-1]['kind']!='TIMEOUT')
    need(v['python']['cases']==[dict(name=n,outcome='PASS') for n in CASES])
    for k in ('input_manifest_sha256','result_sha256','diagnostic_sha256'):need(type(v[k]) is str and re.fullmatch('[0-9a-f]{64}',v[k]) is not None)
    return list(CASES)

def sources(head):
    paths=['installer/native-python-containment','installer/native-g1-controller-fixture','installer/native-acl-observer','installer/native-acl-transaction-fixture','integration/windows_python_probe.py','integration/python_containment_evidence.py','tools/python_containment_bundle.py','.github/workflows/windows-python-containment.yml']
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',head,*paths],cwd=ROOT,text=True).splitlines()
    return {n:hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest() for n in names}

def input_policy(m,head,git_pins):
    need(type(m.get('Files')) is dict and type(m.get('Origins')) is dict and set(m['Files'])==set(m['Origins']))
    actual_git={n for n in m['Files'] if n=='driver.py' or n.startswith('Source/')}
    need(actual_git==set(git_pins))
    for n in m['Files']:
        if n in git_pins:
            need(m['Origins'][n]=='git:'+head and m['Files'][n]['Sha256']==git_pins[n])
        elif n.startswith('Site/'):need(m['Origins'][n]=='pinned-requirements-resolved')
        elif n=='stdlib.zip':need(m['Origins'][n]=='setup-python-stdlib')
        elif n in ('python._pth','pythonw._pth','python311._pth','python312._pth'):need(m['Origins'][n]=='fixed-isolated-paths' and m['Files'][n]['Sha256']==hashlib.sha256(b'stdlib.zip\nDLLs\nSite\nSource\n').hexdigest().upper())
        elif n in ('python.exe','pythonw.exe') or ('/' not in n and n.lower().endswith('.dll')) or (n.startswith('DLLs/') and n.count('/')==1 and n.lower().endswith(('.dll','.pyd'))):need(m['Origins'][n]=='setup-python')
        else:need(False)

def git_inputs(head):
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',head,'grid'],cwd=ROOT,text=True).splitlines()
    result={'Source/'+n:hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest().upper() for n in names if n.endswith('.py')}
    result['driver.py']=hashlib.sha256(subprocess.check_output(['git','show',head+':integration/windows_python_probe.py'],cwd=ROOT)).hexdigest().upper()
    return result

def receipt(folder,head,run,attempt,create=False):
    folder=Path(folder);raw=(folder/'native.json').read_bytes();v=load(raw);names=validate(v,head,run,attempt)
    need(hashlib.sha256((folder/'diagnostics.txt').read_bytes()).hexdigest()==v['diagnostic_sha256'])
    child=(folder/'child.json').read_bytes();inp=(folder/'input.json').read_bytes();m=load(inp)
    need(hashlib.sha256(child).hexdigest()==v['result_sha256'] and load(child)==v['python'])
    need(hashlib.sha256(inp).hexdigest()==v['input_manifest_sha256'] and set(m)=={'Schema','Head','Run','Attempt','Python','Files','Origins'})
    need(type(m['Schema']) is int and m['Schema']==1 and (m['Head'],m['Run'],m['Attempt'])==(head,run,attempt))
    need(m['Python']==v['python']['python_version'] and len(m['Files'])==v['files'] and set(m['Files'])==set(m['Origins']))
    input_policy(m,head,git_inputs(head))
    for n,pin in m['Files'].items():
        from tools.python_containment_bundle import relative
        relative(n);need(type(pin) is dict and set(pin)=={'Sha256','Length'} and type(pin['Length']) is int and 0<=pin['Length']<=32*1024*1024 and re.fullmatch('[0-9A-F]{64}',pin['Sha256']) is not None)
        if m['Origins'][n]=='git:'+head:
            original='integration/windows_python_probe.py' if n=='driver.py' else n.removeprefix('Source/')
            need(n=='driver.py' or original.startswith('grid/'))
            need(hashlib.sha256(subprocess.check_output(['git','show',head+':'+original],cwd=ROOT)).hexdigest().upper()==pin['Sha256'])
    meta=load((folder/'network-host.json').read_bytes());need((meta.get('head'),meta.get('run_id'),meta.get('attempt'))==(head,run,attempt) and meta.get('status')=='OBSERVED_NOT_ATTESTED' and meta.get('loopback_exit')==0 and meta.get('assurance')=='DIAGNOSTIC_ONLY_NOT_EFFECTIVE_WFP_PROOF')
    files=('network-host.json','native.json','child.json','input.json','junit.xml','events.jsonl','dependencies.txt','diagnostics.txt')
    if create:
        xml=E.Element('testsuite',tests=str(len(names)),failures='0',errors='0',skipped='0',head=head,run_id=run,attempt=attempt)
        for n in names:E.SubElement(xml,'testcase',classname='real_python_negative_boundary',name=n)
        E.ElementTree(xml).write(folder/'junit.xml',encoding='utf-8',xml_declaration=True)
        (folder/'events.jsonl').write_text(''.join(json.dumps(dict(name=n,head=head,run_id=run,attempt=attempt,status='HOSTED_BOUNDARY_PASS',physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False))+'\n' for n in names),encoding='utf-8')
        (folder/'manifest.json').write_text(json.dumps(dict(head=head,run_id=run,attempt=attempt,files={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in files},sources=sources(head)),sort_keys=True),encoding='utf-8')
    manifest=load((folder/'manifest.json').read_bytes());need(set(manifest)=={'head','run_id','attempt','files','sources'} and (manifest['head'],manifest['run_id'],manifest['attempt'])==(head,run,attempt) and manifest['sources']==sources(head) and set(manifest['files'])==set(files))
    for n,sha in manifest['files'].items():need(hashlib.sha256((folder/n).read_bytes()).hexdigest()==sha)
    xml=E.fromstring((folder/'junit.xml').read_bytes());need(xml.tag=='testsuite' and xml.attrib==dict(tests=str(len(names)),failures='0',errors='0',skipped='0',head=head,run_id=run,attempt=attempt))
    need([c.attrib for c in xml]==[dict(classname='real_python_negative_boundary',name=n) for n in names] and all(c.tag=='testcase' and len(c)==0 for c in xml) and all(not (c.text or '').strip() and not (c.tail or '').strip() for c in xml.iter()))
    expected=[dict(name=n,head=head,run_id=run,attempt=attempt,status='HOSTED_BOUNDARY_PASS',physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False) for n in names]
    need((folder/'events.jsonl').read_text().splitlines()==[json.dumps(x) for x in expected])
    return dict(head=head,tests=len(names),whole_system='PARTIAL',physical='0/10 NOT_RUN',network_transport='BLOCKED_NO_CAPABILITIES')

if __name__=='__main__':
    mode,folder,head,run,attempt=sys.argv[1:];need(mode in ('create','verify'));print(json.dumps(receipt(folder,head,run,attempt,create=mode=='create')))
