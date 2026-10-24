"""Strict read-only observer test evidence; no infrastructure calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as E
from installer.vm_lab_json import load
ROOT=Path(__file__).resolve().parents[1]
AUTH=('physical_attestation','host_verified','apply_authorized','execute_authorized','cleanup_authorized')
REFUSALS={'missing-argument-refused':{'ARGUMENT_OR_PLATFORM'},'relative-path-refused':{'PATH_FORM'},
 'missing-object-api-failure':{'NT_OPEN_FAILED'},'junction-refused':{'NT_OPEN_FAILED','REPARSE'},
 'ancestor-junction-refused':{'NT_OPEN_FAILED','REPARSE'},'symlink-refused':{'NT_OPEN_FAILED','REPARSE'},
 'hardlink-refused':{'HARDLINK'},'descriptor-toctou-refused':{'OBSERVATION_CHANGED'},'read-control-denied-blocked':{'NT_OPEN_FAILED'}}


def require(ok,code):
    if not ok:raise ValueError(code)


def valid_sid(value):
    if type(value) is not str or not re.fullmatch(r'S-1-(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*)){1,15}',value):return False
    parts=value.split('-');return int(parts[2])<2**48 and all(int(x)<2**32 for x in parts[3:])


def token_facts(t):
    require(type(t) is dict and valid_sid(t.get('user')),'TOKEN_USER')
    require(type(t.get('elevated')) is bool and type(t.get('integrity')) is int and 0<=t['integrity']<2**32,'TOKEN_CONTEXT')
    groups=t.get('groups');require(type(groups) is list and 0<len(groups)<=4096,'TOKEN_GROUPS')
    for g in groups:
        require(type(g) is dict and set(g)=={'sid','attributes'} and valid_sid(g['sid']),'TOKEN_GROUP_SID')
        flags=g['attributes'];require(type(flags) is int and 0<=flags<=0xffffffff and flags&~0xe000007f==0 and not(flags&4 and flags&0x10),'TOKEN_FLAGS')
    raw=dict(user=t['user'],elevated=t['elevated'],level=t['integrity'],groups=[dict(Sid=g['sid'],Attributes=g['attributes']) for g in groups])
    require(hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest().upper()==t.get('fingerprint'),'TOKEN_DIGEST')


def verify_rows(rows,expected,head,run,attempt):
    require([r.get('case') for r in rows]==expected,'CASE_INVENTORY')
    for row in rows:
        require(row.get('head')==head and row.get('run_id')==run and row.get('attempt')==attempt,'CONTEXT')
        require(row.get('outcome')=='PASS' and row.get('kind')=='HOSTED_GUID_OBSERVER_TEST','OUTCOME')
        require(all(row.get(k) is False for k in AUTH),'FALSE_AUTHORITY')
        payload=row.get('payload');require(type(payload) is dict and type(payload.get('code')) is int,'PAYLOAD')
        report=payload.get('value');require(type(report) is dict and report.get('status')=='BLOCKED','BLOCKED_REQUIRED')
        require(all(report.get(k) is False for k in AUTH),'OBSERVER_AUTHORITY')
        case=row['case']
        if case.startswith('injected-'):
            require(payload['code']==2 and report.get('observation')=='REJECTED' and report.get('reason')=='INJECTED_'+case.removeprefix('injected-') and report.get('fault_injection') is True,'INJECTED_REFUSAL')
            continue
        require(report.get('fault_injection') is False,'UNEXPECTED_FAULT')
        if case in REFUSALS:
            require(payload['code']==2 and report.get('observation')=='REJECTED' and report.get('reason') in REFUSALS[case],'EXPECTED_REFUSAL')
        else:
            require(payload['code']==0 and report.get('observation')=='OBSERVED','EXPECTED_OBSERVATION')
            require(report.get('effectiveRightsStatus')=='BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN','EFFECTIVE_UNKNOWN')
            token_facts(report.get('token'))
            chain=report.get('chain');require(type(chain) is list and len(chain)>3,'ANCESTOR_CHAIN')
            for depth,o in enumerate(chain):
                i=o.get('identity',{});require(o.get('depth')==depth and re.fullmatch('[0-9A-F]{32}',i.get('fileId','')),'IDENTITY')
                require(type(i.get('volume')) is int and 0<i['volume']<2**64,'VOLUME')
                require(type(i.get('attributes')) is int and i['attributes']&0x400==0,'REPARSE')
                require(i['attributes']&0x10 or type(i.get('links')) is int and i['links']==1,'LINKS')
                require(re.fullmatch('[0-9A-F]{64}',o.get('descriptorSha256','')),'DESCRIPTOR_HASH')
                require(type(o.get('aces')) is list and type(o.get('protected')) is bool,'DACL')
                require(all(valid_sid(o.get(k)) for k in ('owner','group')),'SECURITY_SIDS')
                for ace in o['aces']:
                    require(type(ace) is dict and set(ace)=={'sid','mask','flags','type'} and valid_sid(ace['sid']),'ACE_SID')
                    require(type(ace['mask']) is int and -2**31<=ace['mask']<2**31 and type(ace['flags']) is int and 0<=ace['flags']<=31 and ace['type'] in ('AccessAllowed','AccessDenied'),'ACE_TYPE')
                rights=o.get('effectiveRights',{});require({'DELETE','WRITE_DAC','WRITE_OWNER','WRITE_DATA','APPEND_DATA'}<=set(rights),'RIGHTS_INCOMPLETE')
                require(all(x in ('DACL_ALLOW','DACL_DENY','BLOCKED_PRIVILEGED_ACCESS') for x in rights.values()),'RIGHTS_UNKNOWN')
            if case.startswith('held-'):
                require(row.get('details')=={'rename_win32':32},'RENAME_NOT_PROVEN')
            tests={'group-deny-precedes-allow':(-1,'WRITE_DATA','DACL_DENY'),
             'group-write-owner-detected':(-1,'WRITE_OWNER','DACL_ALLOW'),'owner-write-dac-detected':(-1,'WRITE_DAC','DACL_ALLOW'),
             'parent-delete-child-detected':(-2,'DELETE_CHILD','DACL_ALLOW')}
            if case in tests:
                index,key,value=tests[case];require(chain[index]['effectiveRights'].get(key)==value,'EXPECTED_NATIVE_RIGHT')


def junit(rows,path,classname):
    suite=E.Element('testsuite',name=classname,tests=str(len(rows)),failures='0',errors='0',skipped='0')
    for name in rows:E.SubElement(suite,'testcase',classname=classname,name=name)
    E.ElementTree(suite).write(path,encoding='utf-8',xml_declaration=True)
    tree=E.parse(path);require([c.get('name') for c in tree.iter('testcase')]==rows,'JUNIT_INVENTORY')
    require(all(int(s.get(k,0))==0 for s in tree.iter('testsuite') for k in ('errors','failures','skipped')),'JUNIT_FALSE_PASS')


def main():
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true',required=True);args=p.parse_args()
    head=os.environ['EXACT_HEAD_SHA'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==head,'EXACT_HEAD')
    inventory=json.loads((ROOT/'tests/fixtures/native_observer_inventory.json').read_text())
    hashes={}
    for name in inventory['source_files']:
        blob=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        require((ROOT/name).read_bytes().replace(b'\r\n',b'\n')==blob,'SOURCE_CHANGED')
        hashes[name]=hashlib.sha256(blob).hexdigest()
    rows=[load(line) for line in Path('native-observer.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    verify_rows(rows,inventory['native_cases'],head,run,attempt)
    pure=load(Path('native-observer-pure.json').read_text(encoding='utf-8-sig'))
    require(pure.get('status')=='OFFLINE_TEST_PASS' and all(pure.get(k) is False for k in AUTH),'PURE_AUTHORITY')
    require([c.get('case') for c in pure['cases']]==inventory['pure_cases'],'PURE_INVENTORY')
    require(all(c.get('outcome')=='PASS' and all(c.get(k) is False for k in AUTH) for c in pure['cases']),'PURE_FALSE_PASS')
    junit(inventory['native_cases'],'native-observer.xml','hosted_guid_observer')
    junit(inventory['pure_cases'],'native-observer-pure.xml','synthetic_managed_policy')
    import pytest
    from installer.ls5_acl_ci import verify_junit
    nodes=[];calls=[];bad=[]
    class Receipt:
        def pytest_collection_finish(self,session):nodes.extend(x.nodeid for x in session.items)
        def pytest_runtest_logreport(self,r):
            if hasattr(r,'wasxfail') or r.outcome!='passed':bad.append([r.nodeid,r.when,r.outcome])
            if r.when=='call' and r.outcome=='passed':calls.append(r.nodeid)
    code=pytest.main(['-q','-p','no:cacheprovider','tests/test_ls5_native_observer.py','--basetemp=.ls5-native-pytest','--junitxml=native-observer-python.xml'],plugins=[Receipt()])
    require(code==0 and not bad and sorted(nodes)==sorted(calls)==inventory['python_nodes'],'PYTHON_INVENTORY')
    verify_junit('native-observer-python.xml',nodes,inventory['python_junit_cases'])
    Path('native-observer-python.jsonl').write_text(''.join(json.dumps(dict(case=n,head=head,run_id=run,attempt=attempt,outcome='PASS',kind='SYNTHETIC_PYTHON',**{k:False for k in AUTH}))+'\n' for n in sorted(calls)),encoding='utf-8')
    binary=ROOT/'installer/native-acl-observer/bin/Release/net8.0-windows'
    binary_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in binary.iterdir() if f.is_file()}
    require({'NativeAclObserver.exe','NativeAclObserver.dll','NativeAclObserver.deps.json','NativeAclObserver.runtimeconfig.json'}<=set(binary_hashes),'BINARY_MISSING')
    names=['native-observer.jsonl','native-observer-pure.json','native-observer.xml','native-observer-pure.xml','native-observer-python.xml','native-observer-python.jsonl']
    receipt=dict(head=head,run_id=run,attempt=attempt,source_sha256=hashes,binary_sha256=binary_hashes,
        artifacts={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in names},native_cases=len(rows),pure_cases=len(pure['cases']),
        physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')
    Path('native-observer-receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True),encoding='utf-8')
    print('EXACT_HEAD_JSONL_JUNIT_SHA256_VERIFIED; PHYSICAL_NOT_RUN')


if __name__=='__main__':main()
