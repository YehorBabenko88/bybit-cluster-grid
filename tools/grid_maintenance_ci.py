"""Maintenance CI receipt: exact Git source pins, explicit JUnit inventory, no authority."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as ET
from tools.grid_physical_maintenance import strict_json,need,verify_junit
ROOT=Path(__file__).resolve().parents[1]
PS_NAMES=frozenset(['plan_no_calls','task_preserved','firewall_disabled_and_redacted','firewall_api_failure','token_missing_pin']+['action_'+s for s in ('Stage','Prepare','Execute','Cleanup','Inventory','Preflight','Evidence')]+['provider_'+s for s in ('none','throw','empty','many','status','reason','shape')])


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


def source_pins(head):
    files=git('ls-tree','-r','--name-only',head,'installer/maintenance','tests/maintenance','tools/grid_physical_maintenance.py','tools/grid_maintenance_ci.py','tools/run_grid_handoff_probe.py','integration/grid_maintenance_inventory.json','.github/workflows/grid-physical-maintenance.yml','docs/GRID_PHYSICAL_MAINTENANCE.md','docs/GRID_MAINTENANCE_INDEPENDENT_CHECKLIST.md').decode().splitlines()
    need(files)
    return {name:hashlib.sha256(git('show',head+':'+name)).hexdigest() for name in files}


def write_ps(raw,path):
    record=strict_json(raw)
    need(set(record)=={'scope','cases','names','status','execute','cleanup'})
    need(record['scope']=='SYNTHETIC_OFFLINE_NOT_PHYSICAL' and record['status']=='PASS')
    need(type(record['cases']) is int and record['cases']==len(PS_NAMES))
    need(type(record['names']) is list and len(record['names'])==len(PS_NAMES) and set(record['names'])==PS_NAMES)
    need(record['execute'] is False and record['cleanup'] is False)
    suite=ET.Element('testsuite',tests=str(len(PS_NAMES)),errors='0',failures='0',skipped='0')
    for name in sorted(PS_NAMES):ET.SubElement(suite,'testcase',name=name,classname='maintenance.mocked')
    ET.ElementTree(suite).write(path,encoding='utf8',xml_declaration=True)


def receipt(root,head,mode):
    need(git('rev-parse','HEAD').decode().strip()==head)
    tree=git('rev-parse','HEAD^{tree}').decode().strip()
    inventory=json.loads((ROOT/'integration/grid_maintenance_inventory.json').read_text())
    files={'tests.xml','python.jsonl'} if mode=='offline' else {'powershell.xml','powershell.json'}
    if mode=='offline':
        # Exact testcase names are sufficient here because there are no duplicate names.
        verify_junit((root/'tests.xml').read_bytes(),set(inventory['cases']))
        events=[strict_json(line) for line in (root/'python.jsonl').read_bytes().splitlines()]
        need(len(events)==len(inventory['cases']) and {x['name'] for x in events}==set(inventory['cases']))
        need(all(set(x)=={'name','status'} and x['status']=='TEST_PASS' for x in events))
    else:verify_junit((root/'powershell.xml').read_bytes(),PS_NAMES)
    ci=dict(head=head,tree=tree,run_id=os.environ.get('GITHUB_RUN_ID','LOCAL'),attempt=os.environ.get('GITHUB_RUN_ATTEMPT','LOCAL'),scope='OFFLINE_OR_HOSTED_NOT_PHYSICAL',mode=mode,execute=False,cleanup=False,deployment='NO-GO')
    ci.update(files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sorted(files)},sources=source_pins(head))
    (root/('manifest-'+mode+'.json')).write_text(json.dumps(ci,indent=2),encoding='utf8')
    print(json.dumps(dict(status='CI_EVIDENCE_CONSISTENT_NOT_PHYSICAL',**ci)))


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['test','ps','receipt','verify-matrix']);p.add_argument('--root',default='maintenance-results');p.add_argument('--head');p.add_argument('--phase',choices=['offline','mocked'],default='offline');a=p.parse_args();root=Path(a.root);root.mkdir(exist_ok=True)
    if a.mode=='verify-matrix':verify_matrix(root,a.head);return 0
    if a.mode=='ps':write_ps((root/'powershell.json').read_bytes(),root/'powershell.xml');return 0
    if a.mode=='receipt':receipt(root,a.head,a.phase);return 0
    import pytest
    code=pytest.main(['-q','-p','no:cacheprovider','tests/maintenance','--junitxml='+str(root/'tests.xml')])
    if code:return int(code)
    xml=ET.parse(root/'tests.xml');names=[c.get('name') for c in xml.iter('testcase')]
    need(len(names)==len(set(names)))
    (root/'python.jsonl').write_text(''.join(json.dumps(dict(name=name,status='TEST_PASS'))+'\n' for name in sorted(names)),encoding='utf8')
    receipt(root,a.head,'offline');return 0


def verify_matrix(root,head):
    from tools.grid_physical_maintenance import verify_ci_zip
    need(git('rev-parse','HEAD').decode().strip()==head)
    need(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and os.environ.get('GITHUB_REPOSITORY')=='YehorBabenko88/bybit-cluster-grid')
    run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
    need(run.isascii() and run.isdecimal() and int(run)>0 and attempt.isascii() and attempt.isdecimal() and int(attempt)>0)
    def api(endpoint):
        response=subprocess.run(['gh','api','--allow-escape-sequences',endpoint],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,check=False)
        need(response.returncode==0);return response.stdout
    repository='repos/YehorBabenko88/bybit-cluster-grid/'
    listing=strict_json(api(repository+'actions/runs/'+run+'/artifacts?per_page=100'))
    need(type(listing['total_count']) is int and listing['total_count']<=100 and len(listing['artifacts'])==listing['total_count'])
    expected={}
    for osname in ('ubuntu-latest','windows-latest'):
        for py in ('3.11','3.12'):expected['maintenance-offline-'+osname+'-'+py+'-'+head]='offline'
    for shell in ('powershell','pwsh'):
        for py in ('3.11','3.12'):expected['maintenance-native-'+shell+'-'+py+'-'+head]='mocked'
    matches=[x for x in listing['artifacts'] if x['name'] in expected]
    need(len(matches)==len(expected) and {x['name'] for x in matches}==set(expected))
    context=dict(head=head,tree=git('rev-parse','HEAD^{tree}').decode().strip(),run_id=run,attempt=attempt)
    inventory=json.loads(git('show',head+':integration/grid_maintenance_inventory.json'))['cases']
    report=[]
    for artifact in matches:
        need(type(artifact['id']) is int and artifact['id']>0 and artifact['expired'] is False)
        digest=artifact['digest'];need(type(digest) is str and digest.startswith('sha256:'))
        raw=api(repository+'actions/artifacts/'+str(artifact['id'])+'/zip')
        verdict=verify_ci_zip(raw,digest[7:],context,source_pins(head),expected[artifact['name']],inventory)
        report.append(dict(artifact_id=artifact['id'],name=artifact['name'],sha256=digest[7:],verdict=verdict))
    record=dict(context,scope='INDEPENDENT_OFFLINE_CONSISTENCY_NOT_AUTHORIZATION',artifacts=report,physical='BLOCKED',execute=False,cleanup=False,deployment='NO-GO')
    (root/'independent-matrix.json').write_text(json.dumps(record,indent=2),encoding='utf8');print(json.dumps(record))

if __name__=='__main__':raise SystemExit(main())
