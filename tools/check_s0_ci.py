"""Exact-head zero-skip S0 CI receipts; never physical authorization."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as E
import pytest
from tools.check_first_boot_offline import BootReceipt
from tools.check_ddl_free_ci import ROOT,verify_checkout

def run(phase):
 head=os.environ['EXACT_HEAD_SHA'];verify_checkout(ROOT,head)
 inv=json.loads((ROOT/'integration/s0_inventory.json').read_text());receipt=BootReceipt();out=ROOT/'s0-results';out.mkdir(exist_ok=True)
 if phase=='offline':nodes=inv['nodes']
 elif phase=='hosted':
  if not(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and os.environ.get('RUNNER_OS')=='Windows' and os.environ.get('GITHUB_JOB')=='s0-windows' and os.environ.get('GITHUB_REPOSITORY')=='YehorBabenko88/bybit-cluster-grid' and os.environ.get('S0_HOSTED_TESTS')=='1'):raise RuntimeError('S0_GENUINE_HOSTED_REQUIRED')
  nodes=inv['hosted_nodes']
 else:raise RuntimeError('S0_CI_PHASE_BLOCKED')
 xml=out/(phase+'.xml');code=pytest.main(['-q','-p','no:cacheprovider',*nodes,'--junitxml='+str(xml)],plugins=[receipt])
 actual=sorted(receipt.passed);bad=receipt.bad
 if code or bad or receipt.nodes!=nodes or actual!=nodes:raise RuntimeError('S0_TEST_INVENTORY_FAILED')
 cases=sorted([r.get('classname'),r.get('name')] for r in E.parse(xml).iter('testcase'))
 if phase=='offline' and (cases!=inv['junit_cases'] or sorted(receipt.subtests)!=inv['subtests']):raise RuntimeError('S0_SUBTEST_JUNIT_INVENTORY_FAILED')
 if any(int(s.get(k,'0')) for s in E.parse(xml).iter('testsuite') for k in ('errors','failures','skipped')):raise RuntimeError('S0_FALSE_PASS')
 ci=dict(head=head,tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),run_id=os.environ.get('GITHUB_RUN_ID','LOCAL'),attempt=os.environ.get('GITHUB_RUN_ATTEMPT','LOCAL'),phase=phase,scope='SYNTHETIC_OFFLINE_OR_HOSTED_NOT_PHYSICAL',g1_execute=False,physical_sid_acl='0/10 NOT_RUN')
 tree=E.parse(xml)
 for suite in tree.iter('testsuite'):suite.attrib.update(head=head,run_id=ci['run_id'],attempt=ci['attempt'])
 tree.write(xml,encoding='utf-8',xml_declaration=True)
 lines=out/(phase+'.jsonl');lines.write_text(''.join(json.dumps(dict(ci,node=n,status='TEST_PASS'))+'\n' for n in actual),encoding='utf-8')
 sources=subprocess.check_output(['git','ls-tree','-r','--name-only',head,'s0_smoke','tests','tools/check_s0_ci.py','tools/build_s0_package.py','tools/verify_s0_portable_ci.py','tools/verify_s0_artifacts_ci.py','tools/s0_native_receipt.py','tools/s0_preparation_receipt.py','tools/s0_ssh_transfer_plan.py','tools/verify_s0_bootstrap_ci.py','tools/s0_independent_acceptance.py','tools/probe_s0_public_ci.py','installer/physical-smoke-s0','installer/physical-smoke-s0-tests','installer/physical-smoke-s0.ps1','installer/physical-smoke-s0-bootstrap.ps1','.github/workflows/physical-smoke-s0.yml','integration/s0_inventory.json','docs/PHYSICAL_SMOKE_S0.md','docs/PHYSICAL_SMOKE_S0_BOOTSTRAP_COMMANDS.md','docs/PHYSICAL_SMOKE_S0_INDEPENDENT_ACCEPTANCE.md'],cwd=ROOT,text=True).splitlines()
 source_pins={n:hashlib.sha256(subprocess.check_output(['git','show',head+':'+n],cwd=ROOT)).hexdigest() for n in sources if not n.startswith('tests/') or Path(n).name.startswith('test_s0_')}
 index=dict(ci,tests=len(actual),subtests=len(receipt.subtests),files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (xml,lines)},sources=source_pins,nodes=actual)
 (out/(phase+'-sha256.json')).write_text(json.dumps(index,indent=2),encoding='utf-8');verify_checkout(ROOT,head)
 print(json.dumps(dict(ci,tests=len(actual),subtests=len(receipt.subtests),status='S0_TEST_GATE_PASS_NOT_EXECUTION_AUTHORITY')))

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)==2 else '')
