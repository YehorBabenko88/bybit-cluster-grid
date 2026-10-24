"""Exact-baseline reproduction and candidate acceptance, disposable hosted CI only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from check_ddl_free_ci import ROOT, verify_checkout

BASELINE = 'da69209af86567232fb3038a899580fe2e061a0b'
CASES = json.loads((ROOT/'tests/fixtures/pr227_adversarial_inventory.json').read_text())


def main():
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('GRID_PG18_TESTS') != '1'):
        raise RuntimeError('HOSTED_DISPOSABLE_CI_ONLY')
    verify_checkout(ROOT, os.environ['EXACT_HEAD_SHA'])
    # Import via root package only after establishing exact checkout.
    sys.path.insert(0, str(ROOT))
    from tools.ci_pg18 import attest
    attest()  # Must precede both phases; fixtures re-attest before each connection.
    sandbox = Path(tempfile.mkdtemp(prefix='pr227-audit-', dir=os.environ['RUNNER_TEMP']))
    archive = sandbox / 'baseline.zip'
    subprocess.check_call(['git', 'archive', '--format=zip', BASELINE, '-o', str(archive)], cwd=ROOT)
    baseline = sandbox / 'baseline'
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            p = Path(entry.filename)
            if p.is_absolute() or '..' in p.parts or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                raise RuntimeError('UNSAFE_BASELINE_ARCHIVE')
        z.extractall(baseline)
    results = {}
    for phase, root in (('baseline-vulnerability-reproduced', baseline), ('candidate-rejection', ROOT)):
        prefix = ROOT / ('pr227-' + phase)
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(root), str(ROOT/'tests'))),
                   PR227_BASELINE_REPRO='1' if root == baseline else '0',
                   ProgramData=str(sandbox/'programdata'), PROGRAMDATA=str(sandbox/'programdata'),
                   PYTHONDONTWRITEBYTECODE='1')
        code = '''import json, pathlib, sys, pytest
import grid.schema_contract as contract
assert pathlib.Path(contract.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]).resolve())
class Receipt:
 def __init__(self): self.passed=[]; self.bad=[]; self.nodes=[]
 def pytest_collection_finish(self,session): self.nodes=sorted(x.nodeid for x in session.items)
 def pytest_runtest_logreport(self,report):
  if hasattr(report,'wasxfail') or report.outcome!='passed': self.bad.append([report.nodeid,report.when,report.outcome])
  if report.when=='call' and report.outcome=='passed': self.passed.append(report.nodeid)
r=Receipt()
status=pytest.main(['-q','--import-mode=importlib','-p','no:cacheprovider','--rootdir',sys.argv[1],
 '--basetemp',sys.argv[2]+'-temp',sys.argv[3],'--junitxml',sys.argv[2]+'.xml'],plugins=[r])
pathlib.Path(sys.argv[2]+'-events.json').write_text(json.dumps(vars(r),sort_keys=True),encoding='utf-8')
assert status==0 and not r.bad and sorted(r.passed)==r.nodes
'''
        subprocess.check_call([sys.executable, '-c', code, str(root), str(prefix),
                               str(ROOT/'tests/test_pr227_adversarial_pg18.py')], cwd=root, env=env)
        tree = ET.parse(str(prefix)+'.xml')
        assert sorted(c.get('name') for c in tree.iter('testcase')) == CASES
        assert all(int(s.get(k, 0)) == 0 for s in tree.iter('testsuite') for k in ('errors','failures','skipped'))
        results[phase] = {'tests':len(CASES), 'security_acceptance':root != baseline}
    verify_checkout(ROOT, os.environ['EXACT_HEAD_SHA'])
    files = {}
    for p in ROOT.glob('pr227-*.xml'):
        files[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    for p in ROOT.glob('pr227-*-events.json'):
        files[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ('grid/schema_contract.py','tools/check_ddl_free_ci.py',
                 'tests/test_pr227_adversarial_pg18.py','tools/check_pr227_adversarial_ci.py'):
        files[name] = hashlib.sha256(subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)).hexdigest()
    (ROOT/'pr227-audit-sha256.json').write_text(json.dumps({
        'sha':os.environ['EXACT_HEAD_SHA'], 'baseline':BASELINE,
        'run_id':os.environ['GITHUB_RUN_ID'], 'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
        'baseline_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'results':results,'files':files},indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
