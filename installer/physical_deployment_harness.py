"""Preparation only: offline fleet plans and synthetic JUnit evidence; no executor."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path, PureWindowsPath
import re
import sys
import xml.etree.ElementTree as ET
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from installer.windows_preflight import unique_object, physical

SCENARIOS={
 'worker_crash':{'selectors':['tests/test_wal_process_ownership.py::test_crash_releases_os_lock_and_preserves_committed_append']},
 'coordinator_disconnect':{'selectors':['tests/test_physical_failure_boundaries.py::test_coordinator_disconnect_retains_wal_until_durable_receipt']},
 'network_interruption':{'selectors':['tests/test_subscription_ack_disconnect.py::test_disconnect_during_ack_retries_new_socket']},
 'wal_checkpoint_failure':{'selectors':['tests/test_wal_checkpoint_validation.py::test_ack_checkpoint_publish_failure_does_not_skip_unacked_record']},
 'disk_full':{'selectors':['tests/test_physical_failure_boundaries.py::test_enospc_append_isolated_to_fixture_does_not_ack']},
 'duplicate_task':{'selectors':['tests/test_trade_task_reconcile.py::test_reconcile_does_not_duplicate_live_trade_task']},
 'postgres_interruption':{'selectors':['tests/test_failure_recovery.py::test_db_outage_retries_then_drains_wal']},
 'interrupted_switch_rollback':{'selectors':['tests/test_failure_recovery.py::test_release_install_recovers_power_loss_replaced_window','tests/test_failure_recovery.py::test_release_supervisor_rolls_back_after_three_fast_crashes']}}

class Rejected(Exception):pass
def need(condition,code):
    if not condition:raise Rejected(code)
def base():return {'schema':1,'execution_authorized':False,'physical_ready':False,'sequence':[]}
def identity(sha):need(isinstance(sha,str) and re.fullmatch('[0-9a-f]{40}',sha),'COMMIT_INVALID')

def plan(data,sha):
    out=base()
    try:
        identity(sha)
        need(isinstance(data,dict) and set(data)=={'schema','run_id','nodes'} and type(data['schema']) is int and data['schema']==1,'FLEET_SCHEMA_INVALID')
        run=data['run_id'];need(isinstance(run,str) and re.fullmatch('[0-9a-f]{32}',run),'RUN_ID_INVALID')
        nodes=data['nodes'];need(isinstance(nodes,list) and 1<=len(nodes)<=16,'FLEET_SIZE_INVALID')
        keys={'id','role','address','windows_major','cpu_logical','ram_bytes','disk_free_bytes','python_version','postgres_major',
          'ssh_available','tailscale_available','runtime_stopped','inventory_complete','test_root','test_root_exists','disposable_cluster_confirmed'}
        seen=set();addresses=set();planned=[]
        for n in nodes:
            need(isinstance(n,dict) and set(n)==keys,'NODE_SCHEMA_INVALID')
            name=n['id'];need(isinstance(name,str) and re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,15}',name),'NODE_ID_INVALID')
            need(name.casefold() not in seen and name.upper() not in {'LS5','LS7'},'NODE_RESERVED_OR_DUPLICATE');seen.add(name.casefold())
            need(n['role'] in ('CONTROL','WORKER'),'ROLE_INVALID')
            address=ipaddress.ip_address(n['address'])
            need(address in ipaddress.ip_network('100.64.0.0/10') or address in ipaddress.ip_network('fd7a:115c:a1e0::/48'),'TAILSCALE_ADDRESS_REQUIRED')
            need(str(address) not in addresses,'ADDRESS_DUPLICATE');addresses.add(str(address))
            for key,minimum in [('windows_major',10),('cpu_logical',2),('ram_bytes',8*1024**3),('disk_free_bytes',35*1024**3)]:
                need(type(n[key]) is int and minimum<=n[key]<2**63,'CAPACITY_OR_PLATFORM_INCOMPATIBLE')
            need(isinstance(n['python_version'],str) and re.fullmatch(r'3[.](11|12)[.][0-9]+',n['python_version']),'PYTHON_INCOMPATIBLE')
            need(type(n['postgres_major']) is int and n['postgres_major']==16,'POSTGRES_TEST_VERSION_REQUIRED')
            for key in ('ssh_available','tailscale_available','runtime_stopped','inventory_complete'):
                need(n[key] is True,'NODE_SAFETY_CHECK_FAILED')
            need(n['test_root_exists'] is False and n['disposable_cluster_confirmed'] is False,'EXISTING_RESOURCES_NOT_OWNED')
            raw=n['test_root'];need(isinstance(raw,str) and len(raw)<=240 and not any(ord(c)<32 for c in raw),'TEST_ROOT_INVALID')
            need(not re.search(r'(^|[\\/])[.]{1,2}([\\/]|$)',raw),'TEST_ROOT_INVALID')
            path=PureWindowsPath(raw)
            need(path.is_absolute() and re.fullmatch('[A-Za-z]:',path.drive or '') and len(path.parts)>=4,'TEST_ROOT_INVALID')
            need(not any(p.casefold() in {'windows','program files','program files (x86)','programdata'} or any(c in p for c in '<>"|?*:') for p in path.parts[1:]),'PROTECTED_ROOT')
            need(path.parts[-2:]==(run,name),'TEST_ROOT_RUN_BINDING_REQUIRED')
            digest=hashlib.sha256((run+name.casefold()).encode()).hexdigest()
            planned.append({'id':name,'role':n['role'],'address':str(address),'test_root':str(path),
              'database':{'name':'grid_lab_'+run[:16]+'_'+digest[:12], 'port':20000+int(digest[:6],16)%30000,
                'new_cluster_required':True,'existing_cluster_use_authorized':False},
              'resource_ownership':'UNPROVEN_UNTIL_SEPARATE_APPROVED_CREATION'})
        control=[n for n in planned if n['role']=='CONTROL'];need(len(control)==1,'EXACTLY_ONE_CONTROL_REQUIRED')
        ordered=control+sorted([n for n in planned if n['role']=='WORKER'],key=lambda x:x['id'].casefold())
        sequence=[]
        for count,label in [(1,'ONE_NODE'),(2,'TWO_NODES'),(len(ordered),'MULTI_NODE')]:
            if count>len(ordered) or any(s['nodes']==[n['id'] for n in ordered[:count]] for s in sequence):continue
            sequence.append({'stage':label,'nodes':[n['id'] for n in ordered[:count]],'operator_approval_required':True,
                'status':'NOT_RUN','requires_previous_stage_evidence':bool(sequence),
                'approval_scope':['exact commit/artifact','new directory and cluster ownership','foreground test processes','fault scope/time limit','rollback and evidence retention'],
                'actions':['Verify exact-head CI and artifact manifests without staging.','Review fresh inventory, backups and ownership; STOP if any resource exists.',
                  'Obtain separate approval to create isolated resources; never call fixed-root install.ps1 for a lab root.',
                  'Obtain separate approval for connectivity probes, process lifecycle and each fault injection.',
                  'Record observed results; stop on any failed check before reviewing next stage.']})
        out.update(status='PLAN_ONLY',commit_sha=sha,run_id=run,nodes=ordered,sequence=sequence,
          evidence_kind='UNAUTHENTICATED_OFFLINE_INVENTORY',
          connectivity_pairs=[{'from':a['id'],'to':b['id'],'address':b['address'],'status':'NOT_RUN',
             'operator_approval_required':True,'checks':['Tailscale reachability','SSH strict host key/batch authentication','read-only Coordinator health'],
             'ports':'UNRESOLVED_REVIEWED_CONFIGURATION_REQUIRED'} for a in ordered for b in ordered if a['id']!=b['id']],
          installation={'existing_tool':'installer/install.ps1','isolated_root_supported':False,'status':'BLOCKED_FIXED_ROOT_INSTALLER','executor':None},
          rollback={'existing_tools':['installer/switch-release.ps1','installer/rollback-release.ps1','installer/recover-release.ps1','installer/assess-release-repair.ps1'],
             'operator_approval_required':True,'schema_downgrade_authorized':False,'cleanup_authorized':False,
             'checklist':['Preserve WAL, ownership generations, releases and evidence.','Confirm Runtime Guard under existing mutex.',
               'Review journal/manifest and schema compatibility read-only.','Do not remove pending markers or start historical runtimes.',
               'Obtain separate exact-scope pointer-repair approval; retain original resources.']},
          scenarios=[{'id':key,'selectors':spec['selectors'],'physical_status':'REQUIRES_OPERATOR_APPROVAL'} for key,spec in SCENARIOS.items()],
          blockers=['EXACT_HEAD_CI_AND_ARTIFACT_VERIFICATION_REQUIRED','ISOLATED_INSTALLER_ADAPTER_NOT_APPROVED','AUDIT_STAGING_POLICY_REVIEW_REQUIRED','FRESH_INVENTORY_AND_NETWORK_EVIDENCE_REQUIRED','NEW_CLUSTER_OWNERSHIP_NOT_PROVEN','EXPLICIT_OPERATOR_APPROVAL_REQUIRED','NO_DEPLOYMENT_EXECUTOR_IMPLEMENTED'])
    except Rejected as e:out.update(status='BLOCKED',code=str(e))
    except Exception:out.update(status='BLOCKED',code='EVIDENCE_INVALID')
    return out

def results(raw,sha,run_id):
    out=base()
    try:
        identity(sha);need(isinstance(run_id,str) and re.fullmatch('[1-9][0-9]*',run_id),'WORKFLOW_RUN_ID_INVALID')
        need(isinstance(raw,bytes) and len(raw)<=4*1024**2 and b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),'JUNIT_INVALID')
        text=raw.decode('utf-8-sig');need('\x00' not in text and '<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(),'JUNIT_INVALID')
        tree=ET.fromstring(text)
        for suite in tree.iter('testsuite'):
            for key in ('failures','errors','skipped'):
                if key in suite.attrib:need(suite.attrib[key]=='0','JUNIT_NOT_ALL_PASSED')
            if 'tests' in suite.attrib:need(suite.attrib['tests'].isdigit() and int(suite.attrib['tests'])==len(list(suite.iter('testcase'))),'JUNIT_COUNTER_MISMATCH')
        cases=list(tree.iter('testcase'));need(bool(cases),'JUNIT_EMPTY')
        need(not any(t.tag in ('failure','error','skipped') for t in tree.iter()),'JUNIT_NOT_ALL_PASSED')
        ids=[c.get('classname','')+'::'+c.get('name','') for c in cases]
        need(len(ids)==len(set(ids)),'JUNIT_DUPLICATE_CASE')
        rows=[]
        for key,spec in SCENARIOS.items():
            matched=[]
            for selector in spec['selectors']:
                file,name=selector.split('::',1);cls=file[:-3].replace('/','.')
                found=[c for c in cases if c.get('classname')==cls and (c.get('name')==name or c.get('name','').startswith(name+'['))]
                need(bool(found),'JUNIT_REQUIRED_CASE_MISSING')
                matched.extend(selector+'#'+hashlib.sha256((cls+'::'+c.get('name','')).encode()).hexdigest()[:12] for c in found)
            rows.append({'id':key,'status':'PASS','evidence':'MOCKED_OR_DISPOSABLE_FIXTURE','physical_status':'NOT_RUN','case_ids':matched})
        out.update(status='SYNTHETIC_PASS',commit_sha=sha,workflow_run_id=run_id,scenarios=rows,total_cases=len(cases))
    except Rejected as e:out.update(status='BLOCKED',code=str(e))
    except Exception:out.update(status='BLOCKED',code='JUNIT_INVALID')
    return out

def markdown(r):
    rows=['# Physical deployment preparation', 'Status: '+r['status'], 'Execution authorized: false; physical readiness: false.']
    for stage in r.get('sequence',[]):rows.append('- '+stage['stage']+': '+', '.join(stage['nodes'])+' — approval required; NOT RUN')
    for scenario in r.get('scenarios',[]):rows.append('- '+scenario['id']+': '+scenario.get('physical_status','NOT_RUN'))
    if r.get('code'):rows.append('Blocker: '+r['code'])
    return '\n'.join(rows)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--evidence',type=Path);group.add_argument('--junit',type=Path)
    p.add_argument('--commit',required=True);p.add_argument('--workflow-run-id');p.add_argument('--format',choices=['json','markdown'],default='json')
    args=p.parse_args(argv)
    try:
        path=args.evidence or args.junit
        need(physical(path) and path.is_file() and path.stat().st_size<=4*1024**2,'INPUT_FILE_INVALID')
        with path.open('rb') as f:raw=f.read(4*1024**2+1)
        need(len(raw)<=4*1024**2,'INPUT_FILE_INVALID')
        report=(plan(json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique_object,parse_constant=lambda _: (_ for _ in ()).throw(ValueError())),args.commit)
                if args.evidence else results(raw,args.commit,args.workflow_run_id))
    except Exception:report={**base(),'status':'BLOCKED','code':'INPUT_FILE_INVALID'}
    print(json.dumps(report,sort_keys=True) if args.format=='json' else markdown(report))
    return 0 if report['status'] in ('PLAN_ONLY','SYNTHETIC_PASS') else 2
if __name__=='__main__':sys.exit(main())
