"""Read-only acceptance of exact-run downloaded S0 artifacts; no executable extraction."""
import hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path
import xml.etree.ElementTree as E
from tools.check_ddl_free_ci import ROOT,verify_checkout
from s0_smoke.policy import load_json
from s0_smoke.evidence import verify_evidence
from tools.s0_native_receipt import validate_native
from tools.probe_s0_public_ci import validate_observation

def need(ok):
 if not ok:raise RuntimeError('S0_ARTIFACT_ACCEPTANCE_BLOCKED')

def require_context(record,expected):
 need(type(record) is dict and type(expected) is dict)
 need(all(type(record.get(k)) is str and record.get(k)==v for k,v in expected.items()))

def require_junit_counts(xml,cases,subtests):
 suites=list(xml.iter('testsuite'));need(len(suites)==1 and type(subtests) is int and subtests>=0)
 declared=suites[0].get('tests')
 need(type(declared) is str and declared.isascii() and declared.isdecimal())
 need(int(declared)==len(cases)+subtests)

def require_component_pair(coordinator,worker,head,tree):
 require_context(coordinator,dict(head=head,tree=tree,role='LS5'))
 need(type(coordinator.get('run_id')) is str)
 require_context(worker,dict(head=head,tree=tree,role='PC4',run_id=coordinator['run_id']))
 a=coordinator['result'];b=worker['result']
 need(a['final'] is True and b['final'] is True)
 need(a['stats']==b['stats'] and a['heartbeats']==b['heartbeats'])

def run(directory):
 head=os.environ['EXACT_HEAD_SHA'];verify_checkout(ROOT,head);root=Path(directory);folders=[p for p in root.iterdir() if p.is_dir()]
 context=dict(head=head,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
 tree_context=dict(context,tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip())
 expected={'s0-offline-'+osname+'-'+py+'-'+head for osname in ('ubuntu-latest','windows-latest') for py in ('3.11','3.12')}|{'physical-smoke-s0-'+shell+'-'+head for shell in ('powershell','pwsh')}
 need({p.name for p in folders}==expected);inventory=json.loads((ROOT/'integration/s0_inventory.json').read_text());report=[]
 for folder in folders:
  hosted=folder.name.startswith('physical-smoke-s0-');phase='hosted' if hosted else 'offline';data=folder/'s0-results' if hosted else folder;build=folder/'s0-package' if hosted else folder;idx=load_json((data/(phase+'-sha256.json')).read_bytes())
  require_context(idx,tree_context);need(set(idx['files'])=={phase+'.xml',phase+'.jsonl'})
  need((idx['head'],idx['run_id'],idx['attempt'])==(head,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT']) and idx['g1_execute'] is False)
  need(idx['nodes']==inventory['hosted_nodes' if hosted else 'nodes'])
  for n,h in idx['files'].items():need(hashlib.sha256((data/n).read_bytes()).hexdigest()==h)
  for n,h in idx['sources'].items():need(hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest()==h)
  raw_xml=(data/(phase+'.xml')).read_bytes();need(len(raw_xml)<=2097152 and b'<!DOCTYPE' not in raw_xml.upper() and b'<!ENTITY' not in raw_xml.upper());xml=E.ElementTree(E.fromstring(raw_xml));need(not list(xml.iter('failure')) and not list(xml.iter('error')) and not list(xml.iter('skipped')))
  cases=sorted([c.get('classname'),c.get('name')] for c in xml.iter('testcase'))
  need(cases==inventory['junit_cases'] if not hosted else sorted(n for _,n in cases)==sorted(n.split('::')[-1] for n in inventory['hosted_nodes']))
  expected_subtests=0 if hosted else len(inventory['subtests'])
  need(type(idx['subtests']) is int and idx['subtests']==expected_subtests)
  require_junit_counts(xml,cases,expected_subtests)
  for suite in xml.iter('testsuite'):need(all(int(suite.get(k,'0'))==0 for k in ('errors','failures','skipped')) and suite.get('head')==head and suite.get('run_id')==os.environ['GITHUB_RUN_ID'] and suite.get('attempt')==os.environ['GITHUB_RUN_ATTEMPT'])
  lines=[json.loads(x) for x in (data/(phase+'.jsonl')).read_text().splitlines()];need([x['node'] for x in lines]==idx['nodes'] and all((x['head'],x['run_id'],x['attempt'])==(head,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT']) and x['g1_execute'] is False and x['physical_sid_acl']=='0/10 NOT_RUN' and x['status']=='TEST_PASS' for x in lines))
  if hosted:
   receipt=load_json((build/'package-receipt.json').read_bytes());need(all(v is False for v in receipt['authority'].values()));package=build/receipt['package'];need(hashlib.sha256(package.read_bytes()).hexdigest()==receipt['sha256'] and receipt['head']==head and receipt['authority']==dict(s0_execute=False,g1_execute=False,cleanup=False))
   require_context(receipt,tree_context)
   native=load_json((data/'native-launcher.json').read_bytes());require_context(native,context);validate_native({k:v for k,v in native.items() if k not in {'run_id','attempt','binary_sha256','source_sha256'}},head);need(native['head']==head and native['run_id']==os.environ['GITHUB_RUN_ID'] and native['scope']=='HOSTED_FIXTURE_NOT_PHYSICAL')
   need(native['deadline']['timed_out'] is True and native['normal']['exit_code']==0 and native['descendant_denied']['exit_code']==0 and native['wrong_hash_rejected'] is True and native['wrong_sid_rejected'] is True)
   for n,h in native['source_sha256'].items():need(hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest()==h)
   need(native['binary_sha256']['S0Launcher.dll']==json.loads(zipfile.ZipFile(package).read('s0-package.json'))['files']['native/S0Launcher.dll']['sha256'])
   probe=load_json((data/'public-probe.json').read_bytes());need((probe['head'],probe['run_id'],probe['attempt'])==(head,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT']) and all(probe[k] is False for k in ('physical_ready','s0_execute','g1_execute')));counts=probe['counts'];need(probe['status']==validate_observation(counts['subscribe_ack'],counts['book_samples'],counts['trade_samples'],probe['error'],probe['http_status']));portable=json.loads((data/'portable.json').read_text());need(portable['head']==head and portable['package_sha256']==receipt['sha256'] and portable['status']=='PORTABLE_PLAN_AND_IMPORTS_PASS' and portable['s0_execute'] is False)
   with zipfile.ZipFile(package) as z:
    names=z.namelist();need(len(names)==len(set(n.casefold() for n in names)) and not any(n.endswith(('tls-key.pem','config.json')) for n in names));m=json.loads(z.read('s0-package.json'));need(m['head']==head and all(v is False for v in m['authority'].values()) and m['authority']==receipt['authority'] and set(names)==set(m['files'])|{'s0-package.json'})
    require_context(m,tree_context);require_context(portable,tree_context)
    for n,pin in m['files'].items():need(hashlib.sha256(z.read(n)).hexdigest()==pin['sha256'])
    for n,pin in m['source'].items():
     need(hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest()==pin)
     target='runtime/App/'+n if n.startswith('s0_smoke/') else n
     need(m['files'][target]['sha256']==pin)
   summaries=[]
   for role in ('LS5','PC4'):
    component=data/'component-fixture'/role;summary=load_json((component/'summary.json').read_bytes());need(summary['head']==head and summary['status']=='BLOCKED_OR_PARTIAL')
    verify_evidence(component,dict(head=head,run_id=summary['run_id'],role=role),'b'*64)
    summaries.append(summary)
   require_component_pair(*summaries,head,tree_context['tree'])
   report.append(dict(artifact=folder.name,package_sha256=receipt['sha256'],scope='PREPARATION_ONLY'))
  else:report.append(dict(artifact=folder.name,scope='OFFLINE_ONLY'))
 print(json.dumps(dict(head=head,status='S0_PREPARATION_ARTIFACTS_CONSISTENT',artifacts=report,s0_execute=False,g1_execute=False)))

if __name__=='__main__':run(sys.argv[1])
