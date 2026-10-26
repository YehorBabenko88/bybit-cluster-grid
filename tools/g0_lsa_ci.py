"""Build/test receipt assembly and offline reinspection. No native calls."""
import hashlib,json,re,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as E
from installer.vm_lab_json import load
ROOT=Path(__file__).resolve().parents[1]
CASES=['sid-mismatch-0','sid-mismatch-1','sid-mismatch-2','sid-mismatch-3','zero-count-nonnull-buffer','sid-bound-direct-only','identity-valid','identity-wrong-sid','identity-wrong-name','identity-missing','identity-partial-error','identity-duplicate','identity-unknown-pin','plan-only','module-manifest','module-versioned-binary','module-missing','module-ambiguous','module-provider-error','module-file-normal','module-file-file-reparse','module-file-ancestor-reparse','module-file-file-directory','module-file-access-denied','module-file-file-missing']
def need(ok):
 if not ok:raise ValueError('G0_LSA_CI_RECEIPT_REFUSED')
def verify_event(x,head,run,attempt):
 need(type(x) is dict and set(x)=={'case','head','run_id','attempt','outcome','assurance','physical'})
 need((x['head'],x['run_id'],x['attempt'],x['outcome'],x['assurance'],x['physical'])==(head,run,attempt,'PASS','SYNTHETIC_ONLY','0/10 NOT_RUN'))
def verify_fake(f):
 need(type(f) is dict and set(f)=={'schema','kind','legacy_cases','cases','physical','execute_authorized','cleanup_authorized','actor_tokens_created'} and type(f['schema']) is int and f['schema']==1 and type(f['legacy_cases']) is int)
 need(f['legacy_cases']==30 and f['cases']==CASES and f['kind']=='SYNTHETIC_FAKE_API_ONLY' and f['physical']=='0/10 NOT_RUN');need(all(f[k] is False for k in ['execute_authorized','cleanup_authorized','actor_tokens_created']))
def sources(head):
 paths=subprocess.check_output(['git','ls-tree','-r','--name-only',head,'lab/lsa-readonly'],cwd=ROOT,text=True).splitlines()+['installer/g0_lsa_evidence.py','tests/test_g0_lsa_evidence.py','tests/test_lsa_readonly.py','tests/fixtures/g0_lsa_inventory.json','tools/g0_lsa_ci.py','.github/workflows/pc4-g0-lsa-readonly.yml']
 return {p:hashlib.sha256(subprocess.check_output(['git','show',head+':'+p],cwd=ROOT)).hexdigest() for p in paths}
def python_cases(raw,head):
 need(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper());root=E.fromstring(raw)
 need(not any(list(root.iter(k)) for k in ['failure','error','skipped']))
 for suite in root.iter('testsuite'):need(all(suite.get(k)=='0' for k in ['failures','errors','skipped']))
 cases=list(root.iter('testcase'));actual=[[x.get('classname'),x.get('name')] for x in cases]
 inventory=load(subprocess.check_output(['git','show',head+':tests/fixtures/g0_lsa_inventory.json'],cwd=ROOT,text=True))['python_junit_cases'];need(actual==inventory and len(cases)==52)
 return [a+'::'+b for a,b in inventory]+['fake::legacy-api-30-aggregate']+['fake::'+x for x in CASES]
def verify(directory,head,run,attempt):
 d=Path(directory);m=load((d/'manifest.json').read_text());need((m['head'],m['run_id'],m['attempt'])==(head,run,attempt));need(set(m)=={'head','run_id','attempt','sources','files','host_verified','execution_authorized','cleanup_authorized','actor_tokens_created','physical','readiness'});need(m['sources']==sources(head));need(all(m[k] is False for k in ['host_verified','execution_authorized','cleanup_authorized','actor_tokens_created']));need(m['physical']=='0/10 NOT_RUN' and m['readiness']=='BLOCKED')
 expected={'G0Lsa.Observer.dll','fake.json','python.xml','g0-lsa.xml','g0-lsa.jsonl'};need(set(m['files'])==expected);need({p.name for p in d.iterdir() if p.is_file()}==expected|{'manifest.json'})
 for n,h in m['files'].items():need(hashlib.sha256((d/n).read_bytes()).hexdigest()==h)
 f=load((d/'fake.json').read_text());verify_fake(f)
 expected_names=python_cases((d/'python.xml').read_bytes(),head)
 xml=(d/'g0-lsa.xml').read_bytes();need(b'<!DOCTYPE' not in xml.upper() and b'<!ENTITY' not in xml.upper());s=E.fromstring(xml);need(s.tag=='testsuite' and s.get('tests')=='78' and all(s.get(k)=='0' for k in ['failures','errors','skipped']));need((s.get('head'),s.get('run_id'),s.get('attempt'))==(head,run,attempt));need(set(s.attrib)=={'tests','failures','errors','skipped','head','run_id','attempt'});need(not (s.text or '').strip());need(len(s)==78 and all(x.tag=='testcase' and set(x.attrib)=={'name'} and len(x)==0 and not (x.text or '').strip() and not (x.tail or '').strip() for x in s));need([x.get('name') for x in s]==expected_names)
 events=[load(x) for x in (d/'g0-lsa.jsonl').read_text().splitlines()];need(len(events)==78 and len({x['case'] for x in events})==78);need([x['case'] for x in events]==[x.get('name') for x in s]);[verify_event(x,head,run,attempt) for x in events];return {'status':'OFFLINE_RECEIPT_CONSISTENT','tests':78,'native_policy_queries':0,'physical':'0/10 NOT_RUN','readiness':'BLOCKED'}
def create(d,head,run,attempt):
 d=Path(d);need(re.fullmatch('[a-f0-9]{40}',head) and run.isdecimal() and attempt.isdecimal());need(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==head)
 f=load((d/'fake.json').read_text());verify_fake(f)
 names=python_cases((d/'python.xml').read_bytes(),head);need(len(set(names))==78)
 suite=E.Element('testsuite',tests='78',failures='0',errors='0',skipped='0',head=head,run_id=run,attempt=attempt)
 rows=[]
 for n in names:E.SubElement(suite,'testcase',name=n);rows.append(dict(case=n,head=head,run_id=run,attempt=attempt,outcome='PASS',assurance='SYNTHETIC_ONLY',physical='0/10 NOT_RUN'))
 E.ElementTree(suite).write(d/'g0-lsa.xml',encoding='utf-8',xml_declaration=True);(d/'g0-lsa.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows))
 files={n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in ['G0Lsa.Observer.dll','fake.json','python.xml','g0-lsa.xml','g0-lsa.jsonl']};(d/'manifest.json').write_text(json.dumps(dict(head=head,run_id=run,attempt=attempt,sources=sources(head),files=files,host_verified=False,execution_authorized=False,cleanup_authorized=False,actor_tokens_created=False,physical='0/10 NOT_RUN',readiness='BLOCKED'),indent=2)+'\n');return verify(d,head,run,attempt)
if __name__=='__main__':
 mode,d,head,run,attempt=sys.argv[1:];print(json.dumps((create if mode=='create' else verify)(d,head,run,attempt)))
