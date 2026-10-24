"""Exact-source, zero-skip required offline inventory. No infrastructure operations."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as E
import pytest
from tools.check_ddl_free_ci import verify_checkout,Receipt
from _pytest.subtests import SubtestReport

ROOT=Path(__file__).resolve().parents[1]


class BootReceipt(Receipt):
    def __init__(self):super().__init__();self.subtests=[]
    def pytest_runtest_logreport(self,report):
        if isinstance(report,SubtestReport):
            context=json.dumps(dict(msg=report.context.msg,kwargs=report.context.kwargs),sort_keys=True,default=repr)
            self.subtests.append(report.nodeid+':'+hashlib.sha256(context.encode()).hexdigest())
            if report.outcome!='passed' or hasattr(report,'wasxfail'):self.bad.append([report.nodeid,'subtest',report.outcome])
        else:super().pytest_runtest_logreport(report)


def run():
    head=os.environ['EXACT_HEAD_SHA'];verify_checkout(ROOT,head)
    if (ROOT/'.env').exists():raise RuntimeError('FIRST_BOOT_DOTENV_FORBIDDEN')
    root=Path(tempfile.mkdtemp(prefix='first-boot-offline-'))
    os.environ['ProgramData']=os.environ['PROGRAMDATA']=str(root)
    os.environ['NODE_ID']='synthetic-offline-node'
    for name in ('POSTGRES_DSN','GRID_PG18_TESTS','GRID_DISPOSABLE_POSTGRES_TESTS'):os.environ.pop(name,None)
    inventory=json.loads((ROOT/'integration/first_boot_inventory.json').read_text())
    receipt=BootReceipt()
    code=pytest.main(['-q','-p','no:cacheprovider',*inventory['nodes'],'--basetemp',str(root/'pytest'),'--junitxml=first-boot-offline.xml'],plugins=[receipt])
    actual=sorted(receipt.passed)
    rows=[dict(name=n,status='LOCAL_PASS' if os.environ.get('GITHUB_ACTIONS')!='true' else 'HOSTED_PASS',assurance='OFFLINE_UNIT_ONLY',
        head=head,run_id=os.environ.get('GITHUB_RUN_ID','LOCAL'),attempt=os.environ.get('GITHUB_RUN_ATTEMPT','LOCAL'),
        physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO') for n in actual]
    Path('first-boot-offline.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    suites=E.parse('first-boot-offline.xml')
    for suite in suites.iter('testsuite'):suite.attrib.update(head=head,run_id=os.environ.get('GITHUB_RUN_ID','LOCAL'),attempt=os.environ.get('GITHUB_RUN_ATTEMPT','LOCAL'))
    suites.write('first-boot-offline.xml',encoding='utf-8',xml_declaration=True)
    if code!=0 or receipt.bad or receipt.nodes!=inventory['nodes'] or actual!=inventory['nodes'] or sorted(receipt.subtests)!=inventory['subtests']:raise RuntimeError('FIRST_BOOT_OFFLINE_INVENTORY_FAILED')
    if sorted([c.get('classname'),c.get('name')] for c in suites.iter('testcase'))!=inventory['junit_cases']:raise RuntimeError('FIRST_BOOT_JUNIT_INVENTORY')
    if any(int(s.get(k,'0')) for s in suites.iter('testsuite') for k in ('failures','errors','skipped')):raise RuntimeError('FIRST_BOOT_FALSE_PASS')
    verify_checkout(ROOT,head)
    files={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('first-boot-offline.xml','first-boot-offline.jsonl')}
    Path('first-boot-offline-subtests.json').write_text(json.dumps(dict(head=head,subtests=sorted(receipt.subtests)),indent=2),encoding='utf-8')
    files['first-boot-offline-subtests.json']=hashlib.sha256(Path('first-boot-offline-subtests.json').read_bytes()).hexdigest()
    Path('first-boot-offline-sha256.json').write_text(json.dumps(dict(head=head,tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),files=files,tests=len(actual),subtests=len(receipt.subtests),
        physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO'),indent=2),encoding='utf-8')


if __name__=='__main__':run()
