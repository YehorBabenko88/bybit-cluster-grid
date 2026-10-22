"""Exact-commit receipts and zero-skip CI gate; no physical commissioning."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import pytest

ROOT=Path(__file__).resolve().parents[1]


class Receipt:
    def __init__(self):
        self.nodes=[]; self.passed=[]; self.bad=[]

    @pytest.fixture(autouse=True)
    def isolated_paths(self,monkeypatch,tmp_path):
        monkeypatch.setenv('ProgramData',str(tmp_path/'programdata'))
        monkeypatch.setenv('PROGRAMDATA',str(tmp_path/'programdata'))

    def pytest_collection_finish(self,session):
        self.nodes=sorted(x.nodeid for x in session.items)

    def pytest_runtest_logreport(self,report):
        if hasattr(report,'wasxfail') or report.outcome!='passed':
            self.bad.append([report.nodeid,report.when,report.outcome])
        if report.when=='call' and report.outcome=='passed':
            self.passed.append(report.nodeid)


def run(mode):
    # Establish sandbox BEFORE test collection imports Worker/config/resources.
    if (ROOT/'.env').exists():
        raise RuntimeError('TEST_CHECKOUT_MUST_NOT_CONTAIN_DOTENV')
    os.environ['NODE_ID']='synthetic-ci-node'
    sandbox=Path(tempfile.mkdtemp(prefix='grid-ddl-test-'))
    os.environ['ProgramData']=os.environ['PROGRAMDATA']=str(sandbox)
    if mode=='offline':
        for key in ('POSTGRES_DSN','GRID_DISPOSABLE_POSTGRES_TESTS','GRID_PG18_TESTS'):
            os.environ.pop(key,None)
    inv=json.loads((ROOT/'tests/fixtures'/f'ddl_{mode}_inventory.json').read_text())
    receipt=Receipt()
    prefix='ddl-'+mode
    code=pytest.main(['-q','-p','no:cacheprovider','--basetemp',str(sandbox/'pytest'),
                     *inv['nodes'],'--junitxml',prefix+'.xml'],plugins=[receipt])
    events={'sha':os.environ['EXACT_HEAD_SHA'],'collected':receipt.nodes,
            'passed':sorted(receipt.passed),'bad':receipt.bad}
    Path(prefix+'-events.json').write_text(json.dumps(events,sort_keys=True),encoding='utf-8')
    assert code==0 and not receipt.bad
    assert receipt.nodes==inv['nodes']==sorted(receipt.passed)
    tree=ET.parse(prefix+'.xml')
    cases=list(tree.iter('testcase'))
    assert len(cases)==len(inv['nodes'])
    assert sorted([c.get('classname'),c.get('name')] for c in cases)==inv['junit_cases']
    assert all(int(s.get(k,0))==0 for s in tree.iter('testsuite') for k in ('errors','failures','skipped'))
    names=subprocess.check_output(['git','diff','--name-only','f99f401aa11b5f0e0ed75046960801f882540216','HEAD'],cwd=ROOT).decode().splitlines()
    files={name:hashlib.sha256(subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)).hexdigest() for name in names}
    for name in (prefix+'.xml',prefix+'-events.json'):
        files[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
    Path(prefix+'-sha256.json').write_text(json.dumps({'sha':events['sha'],'files':files},indent=2),encoding='utf-8')


if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==os.environ['EXACT_HEAD_SHA']
    assert len(sys.argv)==2 and sys.argv[1] in ('offline','pg18')
    run(sys.argv[1])
