"""Hosted software-test receipt gate; not a host preflight or physical adapter."""
import hashlib
import json
import os
import pathlib
import subprocess
import xml.etree.ElementTree as E

import pytest

ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='2a93efaab1ec61cc5e2a872b95e47a0a8a227f55'


def run_suite(inventory_name, prefix):
    inv=json.loads((ROOT/'tests/fixtures'/inventory_name).read_text())
    events=dict(sha=os.environ['EXACT_HEAD_SHA'],nodes=[],calls=[],bad_reports=[])
    class Receipt:
        def pytest_collection_finish(self,session):
            events['nodes']=sorted(x.nodeid for x in session.items)
        def pytest_runtest_logreport(self,report):
            if hasattr(report,'wasxfail') or report.outcome!='passed':
                events['bad_reports'].append([report.nodeid,report.when,report.outcome])
            if report.when=='call' and report.outcome=='passed':
                events['calls'].append(report.nodeid)
    code=pytest.main(['-q','-p','no:cacheprovider',*inv['files'],'--junitxml',prefix+'.xml'],plugins=[Receipt()])
    pathlib.Path(prefix+'-events.json').write_text(json.dumps(events,sort_keys=True),encoding='utf-8')
    assert code==0 and not events['bad_reports']
    assert events['nodes']==inv['nodes']==sorted(events['calls'])
    tree=E.parse(prefix+'.xml'); suites=list(tree.iter('testsuite'))
    assert suites and all(int(s.get(k,0))==0 for s in suites for k in ('errors','failures','skipped'))
    cases=sorted([c.get('classname'),c.get('name')] for c in tree.iter('testcase'))
    assert cases==inv['junit_cases'] and sum(int(s.get('tests',0)) for s in suites)==len(inv['nodes'])


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==os.environ['EXACT_HEAD_SHA']
    run_suite('protected_staging_inventory.json','staging-offline')
    run_suite('protected_staging_baseline_inventory.json','staging-baseline')
    names=subprocess.check_output(['git','diff','--name-only',BASE,'HEAD'],cwd=ROOT).decode().splitlines()
    files={}
    for name in names:
        blob=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
        working=(ROOT/name).read_bytes()
        assert blob.replace(b'\r\n',b'\n')==working.replace(b'\r\n',b'\n')
        files[name]=dict(git_blob_sha256=hashlib.sha256(blob).hexdigest(),working_bytes_sha256=hashlib.sha256(working).hexdigest())
    for name in ('staging-offline.xml','staging-offline-events.json','staging-baseline.xml','staging-baseline-events.json'):
        files[name]=dict(working_bytes_sha256=hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest())
    pathlib.Path('staging-sha256.json').write_text(json.dumps(dict(sha=os.environ['EXACT_HEAD_SHA'],base=BASE,files=files),indent=2),encoding='utf-8')
    print('OFFLINE_MODEL_TESTS_ONLY; HOST_VERIFIED=false; Execute NOT_AUTHORIZED; Physical 0/10 NOT_RUN')


if __name__=='__main__':
    main()
