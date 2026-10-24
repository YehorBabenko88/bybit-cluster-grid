"""Strict read-only observer test evidence; no infrastructure calls."""
import argparse
import base64
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
 'hardlink-refused':{'HARDLINK'},'descriptor-toctou-refused':{'OBSERVATION_CHANGED'},'parent-descriptor-toctou-refused':{'OBSERVATION_CHANGED'},
 'preexisting-delete-handle-refused':{'NT_OPEN_FAILED'},'read-control-denied-blocked':{'NT_OPEN_FAILED'}}


class PythonReceipt:
    def __init__(self):self.nodes=[];self.calls=[];self.bad=[]
    def pytest_collection_finish(self,session):self.nodes.extend(x.nodeid for x in session.items)
    def pytest_runtest_logreport(self,report):
        if hasattr(report,'wasxfail') or report.outcome!='passed':
            self.bad.append([report.nodeid,report.when,report.outcome]);return
        if report.when=='call':self.calls.append(report.nodeid)


def require(ok,code):
    if not ok:raise ValueError(code)


def valid_sid(value):
    if type(value) is not str or not re.fullmatch(r'S-1-(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*)){1,15}',value):return False
    parts=value.split('-');return int(parts[2])<2**48 and all(int(x)<2**32 for x in parts[3:])


def token_facts(t):
    require(type(t) is dict and set(t)=={'user','elevated','integrity','groups','fingerprint'} and valid_sid(t.get('user')),'TOKEN_USER')
    require(type(t.get('elevated')) is bool and type(t.get('integrity')) is int and 0<=t['integrity']<2**32,'TOKEN_CONTEXT')
    groups=t.get('groups');require(type(groups) is list and 0<len(groups)<=4096,'TOKEN_GROUPS')
    for g in groups:
        require(type(g) is dict and set(g)=={'sid','attributes'} and valid_sid(g['sid']),'TOKEN_GROUP_SID')
        flags=g['attributes'];require(type(flags) is int and 0<=flags<=0xffffffff and flags&~0xe000007f==0 and not(flags&4 and flags&0x10),'TOKEN_FLAGS')
    require(len({g['sid'] for g in groups})==len(groups),'DUPLICATE_TOKEN_GROUP')
    raw=dict(user=t['user'],elevated=t['elevated'],level=t['integrity'],groups=[dict(Sid=g['sid'],Attributes=g['attributes']) for g in groups])
    require(hashlib.sha256(json.dumps(raw,separators=(',',':')).encode()).hexdigest().upper()==t.get('fingerprint'),'TOKEN_DIGEST')


def verify_rows(rows,expected,head,run,attempt):
    require([r.get('case') for r in rows]==expected,'CASE_INVENTORY')
    for row in rows:
        require(set(row)==set(AUTH)|{'case','outcome','head','run_id','attempt','kind','payload','details'},'ROW_SCHEMA')
        require(row.get('head')==head and row.get('run_id')==run and row.get('attempt')==attempt,'CONTEXT')
        require(row.get('outcome')=='PASS' and row.get('kind')=='HOSTED_GUID_OBSERVER_TEST','OUTCOME')
        require(all(row.get(k) is False for k in AUTH),'FALSE_AUTHORITY')
        payload=row.get('payload');require(type(payload) is dict and set(payload)=={'code','value'} and type(payload.get('code')) is int,'PAYLOAD')
        report=payload.get('value');require(type(report) is dict and report.get('status')=='BLOCKED','BLOCKED_REQUIRED')
        require(all(report.get(k) is False for k in AUTH),'OBSERVER_AUTHORITY')
        common=set(AUTH)|{'schema','fault_injection','status','observation','reason'}
        extra={'native_error'} if report.get('observation')=='REJECTED' else {'effectiveRightsStatus','token','chain'}
        require(set(report)==common|extra and type(report.get('schema')) is int and report['schema']==1,'REPORT_SCHEMA')
        if 'native_error' in report:require(report['native_error'] is None or type(report['native_error']) is int,'NATIVE_ERROR_SCHEMA')
        case=row['case']
        if case.startswith('injected-'):
            require(payload['code']==2 and report.get('observation')=='REJECTED' and report.get('reason')=='INJECTED_'+case.removeprefix('injected-') and report.get('fault_injection') is True,'INJECTED_REFUSAL')
            continue
        require(report.get('fault_injection') is False,'UNEXPECTED_FAULT')
        if case in REFUSALS:
            require(payload['code']==2 and report.get('observation')=='REJECTED' and report.get('reason') in REFUSALS[case],'EXPECTED_REFUSAL')
            if case=='preexisting-delete-handle-refused':require(report.get('native_error')==-1073741757,'DELETE_HANDLE_SHARING_REQUIRED')
        else:
            require(payload['code']==0 and report.get('observation')=='OBSERVED','EXPECTED_OBSERVATION')
            require(report.get('effectiveRightsStatus')=='BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN','EFFECTIVE_UNKNOWN')
            require(report.get('reason')=='ALL_PRINCIPALS_WRITERS_AND_BOOTSTRAP_NOT_PROVEN','OBSERVATION_REASON')
            token_facts(report.get('token'))
            chain=report.get('chain');require(type(chain) is list and len(chain)>3,'ANCESTOR_CHAIN')
            identities=set();volume=chain[0].get('identity',{}).get('volume')
            for depth,o in enumerate(chain):
                require(type(o) is dict and set(o)=={'depth','identity','owner','group','descriptorSha256','protected','aces','effectiveRights'},'OBSERVATION_SCHEMA')
                i=o.get('identity',{});require(type(o.get('depth')) is int and o['depth']==depth and re.fullmatch('[0-9A-F]{32}',i.get('fileId','')),'IDENTITY')
                require(type(i) is dict and set(i)=={'volume','fileId','links','attributes'},'IDENTITY_SCHEMA')
                require(type(i.get('links')) is int and 0<i['links']<2**32,'LINK_COUNT')
                require(i.get('fileId')!='0'*32,'ZERO_ID')
                require(type(i.get('volume')) is int and 0<i['volume']<2**64 and i['volume']==volume,'VOLUME')
                key=(i['volume'],i['fileId']);require(key not in identities,'DUPLICATE_ID');identities.add(key)
                require(depth==len(chain)-1 or i.get('attributes',0)&0x10!=0,'PARENT_DIRECTORY')
                require(type(i.get('attributes')) is int and i['attributes']&0x400==0,'REPARSE')
                require(i['attributes']&0x10 or type(i.get('links')) is int and i['links']==1,'LINKS')
                require(re.fullmatch('[0-9A-F]{64}',o.get('descriptorSha256','')),'DESCRIPTOR_HASH')
                require(type(o.get('aces')) is list and type(o.get('protected')) is bool,'DACL')
                require(all(valid_sid(o.get(k)) for k in ('owner','group')),'SECURITY_SIDS')
                for ace in o['aces']:
                    require(type(ace) is dict and set(ace)=={'sid','mask','flags','type'} and valid_sid(ace['sid']),'ACE_SID')
                    require(type(ace['mask']) is int and -2**31<=ace['mask']<2**31 and type(ace['flags']) is int and 0<=ace['flags']<=31 and ace['type'] in ('AccessAllowed','AccessDenied'),'ACE_TYPE')
                rights=o.get('effectiveRights',{});required={'DELETE','WRITE_DAC','WRITE_OWNER','WRITE_DATA','APPEND_DATA'}|({'DELETE_CHILD'} if i['attributes']&0x10 else set())
                require(type(rights) is dict and set(rights)==required,'RIGHTS_INCOMPLETE')
                require(not(i['attributes']&0x10) or 'DELETE_CHILD' in rights,'PARENT_DELETE_CHILD_MISSING')
                require(all(x in ('DACL_ALLOW','DACL_DENY','BLOCKED_PRIVILEGED_ACCESS') for x in rights.values()),'RIGHTS_UNKNOWN')
            if case.startswith('held-'):
                require(row.get('details')=={'rename_win32':32},'RENAME_NOT_PROVEN')
            if case=='preexisting-writer-not-excluded':require(row.get('details')=={'writer_survives':True},'WRITER_EXCLUSION_NOT_PROVEN')
            tests={'group-deny-precedes-allow':(-1,'WRITE_DATA','DACL_DENY'),
             'group-write-owner-detected':(-1,'WRITE_OWNER','DACL_ALLOW'),'owner-write-dac-detected':(-1,'WRITE_DAC','DACL_ALLOW'),
             'parent-delete-child-detected':(-2,'DELETE_CHILD','DACL_ALLOW')}
            if case in tests:
                index,key,value=tests[case];require(chain[index]['effectiveRights'].get(key)==value,'EXPECTED_NATIVE_RIGHT')


def verify_snapshot(s,head,run,attempt):
    require(type(s) is dict and set(s)=={'case','binding','journal_id','root_observed','target_observed','current_descriptor','journal_base64'},'SNAPSHOT_SCHEMA')
    b=s['binding'];require(type(b) is dict and set(b)=={'Schema','Head','Run','Attempt','Id','Root','Target','Old','New'},'BINDING_SCHEMA')
    require(type(b['Schema']) is int and b['Schema']==1 and (b['Head'],b['Run'],b['Attempt'])==(head,run,attempt),'BINDING_CONTEXT')
    require(type(b['Id']) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',b['Id']),'TX_ID')
    for i in (b['Root'],b['Target'],s['journal_id']):
        require(type(i) is dict and set(i)=={'Volume','FileId','Links','Attributes'} and type(i['Volume']) is int and 0<i['Volume']<2**64 and
                type(i['Links']) is int and i['Links']==1 and type(i['Attributes']) is int and 0<=i['Attributes']<2**32 and i['Attributes']&0x400==0 and
                re.fullmatch('[0-9A-F]{32}',i['FileId']) and i['FileId']!='0'*32,'TX_IDENTITY')
    require(b['Root']['Attributes']&0x10 and not b['Target']['Attributes']&0x10 and not s['journal_id']['Attributes']&0x10,'TX_TYPES')
    require(len({i['FileId'] for i in (b['Root'],b['Target'],s['journal_id'])})==3 and len({i['Volume'] for i in (b['Root'],b['Target'],s['journal_id'])})==1,'TX_SCOPE')
    require(s['root_observed']==b['Root'] and s['target_observed']==b['Target'],'TX_REOBSERVED')
    require(b['Old']!=b['New'] and all(type(v) is str and 20<=len(base64.b64decode(v,validate=True))<=131072 for v in (b['Old'],b['New'])),'TX_DESCRIPTORS')
    raw=base64.b64decode(s['journal_base64'],validate=True);require(0<len(raw)<=262144 and raw.endswith(b'\n') and b'\r' not in raw,'JOURNAL_BYTES')
    lines=raw.splitlines();require(1<=len(lines)<=7,'JOURNAL_COUNT');previous='0'*64;phase=None
    normal=['PREPARED','INTENT','APPLIED','VERIFIED','COMMITTED']
    for n,line in enumerate(lines):
        r=load(line.decode());require(type(r) is dict and set(r)=={'Binding','Sequence','Phase','Previous','Digest'},'JOURNAL_RECORD')
        require(r['Binding']==b and type(r['Sequence']) is int and r['Sequence']==n and r['Previous']==previous,'JOURNAL_BINDING')
        next_phase=r['Phase']
        valid=(phase is None and next_phase=='PREPARED' or phase in normal[:-1] and next_phase==normal[normal.index(phase)+1] or
               phase in normal[1:] and next_phase=='RESTORE_INTENT' or phase=='RESTORE_INTENT' and next_phase=='RESTORED')
        require(valid,'JOURNAL_PHASE')
        match=re.search(rb',"Digest":"([0-9A-F]{64})"}$',line);require(match is not None,'JOURNAL_DIGEST_FORMAT')
        previous=hashlib.sha256(line[:match.start()]+b'}').hexdigest().upper();require(previous==r['Digest'],'JOURNAL_DIGEST')
        phase=next_phase
    expected=b['Old'] if phase in ('PREPARED','INTENT','RESTORED') else b['New']
    require(s['current_descriptor']==expected,'TX_READBACK')
    terminal={'commit-native-readback':'COMMITTED','simulated-reopen-PREPARED':'PREPARED','simulated-reopen-INTENT':'INTENT',
              **{'simulated-reopen-'+p:'RESTORED' for p in ('AFTER_SET','APPLIED','VERIFIED','COMMITTED')}}
    require(terminal.get(s['case'])==phase,'TX_SNAPSHOT_TERMINAL')


def verify_transaction(report,expected,head,run,attempt):
    require(type(report) is dict and set(report)==set(AUTH)|{'schema','status','head','run_id','attempt','cases','snapshots','crash_model','journal_authentication','durable_antirollback'},'TX_SCHEMA')
    require(type(report['schema']) is int and report['schema']==1 and report['status']=='OFFLINE_FIXTURE_PASS','TX_STATUS')
    require(report['head']==head and report['run_id']==run and report['attempt']==attempt,'TX_CONTEXT')
    require(all(report[k] is False for k in AUTH),'TX_AUTHORITY')
    require(report['crash_model']=='SIMULATED_BARRIER_REOPEN_RETAINED_ROOT' and report['journal_authentication']=='NOT_PROVEN' and report['durable_antirollback']=='BLOCKED','TX_UNPROVEN')
    require(type(report['cases']) is list and [r.get('case') for r in report['cases']]==expected,'TX_CASES')
    for row in report['cases']:
        require(set(row)==set(AUTH)|{'case','outcome','kind','head','run_id','attempt'} and all(row[k] is False for k in AUTH),'TX_ROW_SCHEMA')
        require(row['outcome']=='PASS' and row['kind']=='HOSTED_GUID_TRANSACTION_TEST' and row['head']==head and row['run_id']==run and row['attempt']==attempt,'TX_ROW_CONTEXT')
    require(type(report['snapshots']) is list and [s.get('case') for s in report['snapshots']]==['commit-native-readback']+['simulated-reopen-'+p for p in ('PREPARED','INTENT','AFTER_SET','APPLIED','VERIFIED','COMMITTED')],'TX_SNAPSHOTS')
    for snapshot in report['snapshots']:verify_snapshot(snapshot,head,run,attempt)
    require(len({s['binding']['Id'] for s in report['snapshots']})==7 and
            len({(s['binding']['Root']['Volume'],s['binding']['Root']['FileId']) for s in report['snapshots']})==7,'TX_SCENARIO_REPLAY')


def verify_pure(pure,expected):
    require(type(pure) is dict and set(pure)==set(AUTH)|{'schema','status','cases'} and type(pure['schema']) is int and pure['schema']==1,'PURE_SCHEMA')
    require(pure['status']=='OFFLINE_TEST_PASS' and all(pure[k] is False for k in AUTH),'PURE_AUTHORITY')
    require(type(pure['cases']) is list and [c.get('case') for c in pure['cases']]==expected,'PURE_INVENTORY')
    require(all(set(c)==set(AUTH)|{'case','outcome'} and c['outcome']=='PASS' and all(c[k] is False for k in AUTH) for c in pure['cases']),'PURE_FALSE_PASS')


def junit(rows,path,classname,head,run,attempt):
    suite=E.Element('testsuite',name=classname,head=head,run_id=run,attempt=attempt,tests=str(len(rows)),failures='0',errors='0',skipped='0')
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
    verify_pure(pure,inventory['pure_cases'])
    tx=load(Path('native-observer-transaction.json').read_text(encoding='utf-8-sig'))
    verify_transaction(tx,inventory['transaction_cases'],head,run,attempt)
    model=load(Path('native-observer-journal-model.json').read_text(encoding='utf-8-sig'))
    require(type(model) is dict and set(model)==set(AUTH)|{'kind','cases','status'} and model['kind']=='SYNTHETIC_JOURNAL_MODEL' and model['status']=='OFFLINE_TEST_PASS' and all(model[k] is False for k in AUTH),'JOURNAL_MODEL_SCHEMA')
    require(model['cases']==inventory['journal_cases'],'JOURNAL_CASES')
    junit(inventory['native_cases'],'native-observer.xml','hosted_guid_observer',head,run,attempt)
    junit(inventory['pure_cases'],'native-observer-pure.xml','synthetic_managed_policy',head,run,attempt)
    junit(inventory['transaction_cases'],'native-observer-transaction.xml','hosted_guid_transaction',head,run,attempt)
    junit(inventory['journal_cases'],'native-observer-journal-model.xml','synthetic_journal_model',head,run,attempt)
    import pytest
    from installer.ls5_acl_ci import verify_junit
    receipt=PythonReceipt();nodes=receipt.nodes;calls=receipt.calls;bad=receipt.bad
    code=pytest.main(['-q','-p','no:cacheprovider','tests/test_ls5_native_observer.py','--basetemp=.ls5-native-pytest','--junitxml=native-observer-python.xml'],plugins=[receipt])
    require(code==0 and not bad and sorted(nodes)==sorted(calls)==inventory['python_nodes'],'PYTHON_INVENTORY')
    verify_junit('native-observer-python.xml',nodes,inventory['python_junit_cases'])
    tree=E.parse('native-observer-python.xml')
    for suite in tree.iter('testsuite'):suite.attrib.update(head=head,run_id=run,attempt=attempt)
    tree.write('native-observer-python.xml',encoding='utf-8',xml_declaration=True)
    Path('native-observer-python.jsonl').write_text(''.join(json.dumps(dict(case=n,head=head,run_id=run,attempt=attempt,outcome='PASS',kind='SYNTHETIC_PYTHON',**{k:False for k in AUTH}))+'\n' for n in sorted(calls)),encoding='utf-8')
    binary=ROOT/'installer/native-acl-observer/bin/Release/net8.0-windows'
    binary_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in binary.iterdir() if f.is_file()}
    require({'NativeAclObserver.exe','NativeAclObserver.dll','NativeAclObserver.deps.json','NativeAclObserver.runtimeconfig.json'}<=set(binary_hashes),'BINARY_MISSING')
    txbinary=ROOT/'installer/native-acl-transaction-fixture/bin/Release/net8.0-windows'
    tx_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in txbinary.iterdir() if f.is_file()}
    require({'NativeAclTransactionFixture.exe','NativeAclTransactionFixture.dll','NativeAclTransactionFixture.deps.json','NativeAclTransactionFixture.runtimeconfig.json'}<=set(tx_hashes),'TX_BINARY_MISSING')
    Path('native-observer-transaction.jsonl').write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in tx['cases']),encoding='utf-8')
    names=['native-observer.jsonl','native-observer-pure.json','native-observer.xml','native-observer-pure.xml','native-observer-python.xml','native-observer-python.jsonl',
           'native-observer-transaction.json','native-observer-transaction.jsonl','native-observer-transaction.xml','native-observer-journal-model.json','native-observer-journal-model.xml']
    receipt=dict(head=head,run_id=run,attempt=attempt,source_sha256=hashes,binary_sha256=binary_hashes,transaction_binary_sha256=tx_hashes,
        artifacts={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in names},native_cases=len(rows),pure_cases=len(pure['cases']),
        transaction_cases=len(tx['cases']),journal_model_cases=len(model['cases']),bootstrap_handoff='BLOCKED_NOT_CONSUMED',
        physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')
    Path('native-observer-receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True),encoding='utf-8')
    print('EXACT_HEAD_JSONL_JUNIT_SHA256_VERIFIED; PHYSICAL_NOT_RUN')


if __name__=='__main__':main()
