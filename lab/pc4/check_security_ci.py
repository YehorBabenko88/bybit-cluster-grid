"""Hosted offline evidence gate. No host identities, subprocess actors or SQL."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def verify_package(folder,sha):
    from installer.vm_lab_json import load
    manifest=load((folder/'package.sha256.json').read_text(encoding='utf-8'))
    names={'Common.ps1','Lifecycle.ps1','Actor.ps1','TokenFacts.cs','TokenFacts.dll','Invoke-Pc4SidAcl.ps1'}
    assert manifest['source_sha']==sha and manifest['kind']=='PC4_OFFLINE_BUILT_PACKAGE'
    assert set(manifest['files'])==names
    assert set(p.name for p in folder.iterdir())==names|{'package.sha256.json','PACKAGE_MANIFEST_SHA256.txt'}
    assert (folder/'PACKAGE_MANIFEST_SHA256.txt').read_text().strip()==hashlib.sha256((folder/'package.sha256.json').read_bytes()).hexdigest()
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
        if name!='TokenFacts.dll':
            expected=subprocess.check_output(['git','show',sha+':lab/pc4/'+name],cwd=ROOT)
            assert expected.replace(b'\r\n',b'\n')==(folder/name).read_bytes().replace(b'\r\n',b'\n')


class Receipt:
    def __init__(self):self.nodes=[];self.calls=[];self.bad=[]
    def pytest_collection_finish(self,session):self.nodes=sorted(i.nodeid for i in session.items)
    def pytest_runtest_logreport(self,report):
        if hasattr(report,'wasxfail') or report.outcome!='passed':self.bad.append([report.nodeid,report.when,report.outcome])
        if report.when=='call' and report.outcome=='passed':self.calls.append(report.nodeid)


def main():
    sha=os.environ['EXACT_HEAD_SHA']
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==sha
    if os.environ.get('PC4_PACKAGE_PATH'):verify_package(Path(os.environ['PC4_PACKAGE_PATH']),sha)
    inventory=json.loads((ROOT/'tests/fixtures/pc4_hardening_inventory.json').read_text())
    r=Receipt();code=pytest.main(['-q','-p','no:cacheprovider',*inventory['files'],'--junitxml','pc4-hardening.xml'],plugins=[r])
    assert code==0 and not r.bad and r.nodes==inventory['nodes']==sorted(r.calls)
    tree=ET.parse('pc4-hardening.xml')
    assert sorted([c.get('classname'),c.get('name')] for c in tree.iter('testcase'))==inventory['junit_cases']
    assert all(int(s.get(k,0))==0 for s in tree.iter('testsuite') for k in ('errors','failures','skipped'))
    events=dict(sha=sha,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                nodes=r.nodes,calls=sorted(r.calls),bad=r.bad,physical_attestation=False,
                execution_authorized=False,cleanup_authorized=False,host_verified=False)
    Path('pc4-hardening-events.json').write_text(json.dumps(events,sort_keys=True),encoding='utf-8')
    files={}
    for name in subprocess.check_output(['git','diff','--name-only','b0d31eaaa2221da357ef6127fca3f0207c4248e2',sha],cwd=ROOT).decode().splitlines():
        expected=subprocess.check_output(['git','show',sha+':'+name],cwd=ROOT)
        assert (ROOT/name).read_bytes().replace(b'\r\n',b'\n')==expected.replace(b'\r\n',b'\n')
        files[name]=hashlib.sha256(expected).hexdigest()
    for name in ('pc4-hardening.xml','pc4-hardening-events.json','pc4-offline.xml','pc4-offline-events.json','lsa-source.xml'):
        files[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
    Path('pc4-hardening-sha256.json').write_text(json.dumps(dict(sha=sha,files=files),indent=2),encoding='utf-8')


if __name__=='__main__':main()
