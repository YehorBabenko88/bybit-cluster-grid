"""Fail-closed acceptance of required jobs and downloaded exact-attempt evidence.

Only reads GitHub metadata/artifacts and local checkout. Never executes artifacts.
This establishes CI evidence consistency, not production/physical authorization.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    'offline (ubuntu-latest, 3.11)', 'offline (ubuntu-latest, 3.12)',
    'offline (windows-latest, 3.11)', 'offline (windows-latest, 3.12)', 'pg18',
}


def validate_jobs(run, jobs, sha, run_id, attempt):
    if (run.get('head_sha') != sha or str(run.get('id')) != str(run_id)
            or str(run.get('run_attempt')) != str(attempt)):
        raise RuntimeError('BLOCKED_RUN_IDENTITY')
    for name in REQUIRED:
        matches = [j for j in jobs if j.get('name') == name]
        if len(matches) != 1:
            raise RuntimeError('BLOCKED_REQUIRED_JOB_MISSING_OR_AMBIGUOUS')
        job = matches[0]
        if (str(job.get('run_id')) != str(run_id) or str(job.get('run_attempt')) != str(attempt)
                or job.get('head_sha') != sha):
            raise RuntimeError('BLOCKED_JOB_IDENTITY')
        if job.get('status') != 'completed' or job.get('conclusion') != 'success':
            raise RuntimeError('BLOCKED_REQUIRED_JOB_NOT_SUCCESS')


def validate_evidence(folder, mode, sha, run_id, attempt):
    prefix = 'ddl-' + mode
    manifest = json.loads((folder/(prefix+'-sha256.json')).read_text(encoding='utf-8'))
    events = json.loads((folder/(prefix+'-events.json')).read_text(encoding='utf-8'))
    for data in (manifest, events):
        if (data.get('sha') != sha or str(data.get('run_id')) != str(run_id)
                or str(data.get('run_attempt')) != str(attempt)):
            raise RuntimeError('BLOCKED_EVIDENCE_IDENTITY')
    inv = json.loads((ROOT/'tests/fixtures'/f'ddl_{mode}_inventory.json').read_text())
    if (events['collected'] != inv['nodes'] or events['passed'] != inv['nodes'] or events['bad']):
        raise RuntimeError('BLOCKED_TEST_INVENTORY')
    tree = ET.parse(folder/(prefix+'.xml'))
    cases = [[c.get('classname'),c.get('name')] for c in tree.iter('testcase')]
    if sorted(cases) != inv['junit_cases'] or any(
            int(s.get(k,0)) for s in tree.iter('testsuite') for k in ('errors','failures','skipped')):
        raise RuntimeError('BLOCKED_JUNIT')
    required = {prefix+'.xml', prefix+'-events.json', 'ddl-dependencies.txt'}
    if mode == 'pg18':
        required.add('pg18-provider.json')
    if not required.issubset(manifest['files']):
        raise RuntimeError('BLOCKED_REQUIRED_HASH_MISSING')
    changed = set(subprocess.check_output(['git','diff','--name-only',
        'f99f401aa11b5f0e0ed75046960801f882540216',sha],cwd=ROOT).decode().splitlines())
    if not changed.issubset(manifest['files']):
        raise RuntimeError('BLOCKED_SOURCE_HASH_MISSING')
    for name, expected in manifest['files'].items():
        if name in required:
            data = (folder/name).read_bytes()
        elif name in changed:
            data = subprocess.check_output(['git','show',sha+':'+name],cwd=ROOT)
        else:
            raise RuntimeError('BLOCKED_UNEXPECTED_HASH_PATH')
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('BLOCKED_SHA256')


def api(path):
    return json.loads(subprocess.check_output(['gh','api',path],stderr=subprocess.PIPE))


def validate_adversarial(folder, sha, run_id, attempt):
    audit = json.loads((folder/'pr227-audit-sha256.json').read_text())
    if (audit.get('sha') != sha or str(audit.get('run_attempt')) != str(attempt)
            or str(audit.get('run_id')) != str(run_id)
            or audit.get('baseline') != 'da69209af86567232fb3038a899580fe2e061a0b'):
        raise RuntimeError('BLOCKED_ADVERSARIAL_IDENTITY')
    cases = json.loads((ROOT/'tests/fixtures/pr227_adversarial_inventory.json').read_text())
    required = {'grid/schema_contract.py','tools/check_ddl_free_ci.py',
                'tests/test_pr227_adversarial_pg18.py','tools/check_pr227_adversarial_ci.py'}
    for phase, acceptance in (('baseline-vulnerability-reproduced',False),('candidate-rejection',True)):
        if audit.get('results',{}).get(phase) != {'tests':len(cases),'security_acceptance':acceptance}:
            raise RuntimeError('BLOCKED_ADVERSARIAL_PHASE')
        prefix = 'pr227-'+phase
        required.update((prefix+'.xml',prefix+'-events.json'))
        tree = ET.parse(folder/(prefix+'.xml'))
        events = json.loads((folder/(prefix+'-events.json')).read_text())
        if (sorted(c.get('name') for c in tree.iter('testcase')) != cases
                or any(int(s.get(k,0)) for s in tree.iter('testsuite') for k in ('errors','failures','skipped'))
                or events.get('bad') != [] or sorted(events.get('passed',[])) != events.get('nodes')
                or sorted(n.rsplit('::',1)[-1] for n in events.get('nodes',[])) != cases):
            raise RuntimeError('BLOCKED_ADVERSARIAL_JUNIT_OR_INVENTORY')
    if set(audit.get('files',{})) != required:
        raise RuntimeError('BLOCKED_ADVERSARIAL_HASH_INVENTORY')
    for path, digest in audit['files'].items():
        data = subprocess.check_output(['git','show',sha+':'+path],cwd=ROOT) if '/' in path else (folder/path).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:
            raise RuntimeError('BLOCKED_ADVERSARIAL_SHA256')


def main():
    sha, run_id, attempt = (os.environ[k] for k in ('EXACT_HEAD_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('GITHUB_REPOSITORY') != 'YehorBabenko88/bybit-cluster-grid'):
        raise RuntimeError('BLOCKED_HOST_CONTEXT')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip() != sha:
        raise RuntimeError('BLOCKED_CHECKOUT_SHA')
    repo = os.environ['GITHUB_REPOSITORY']
    base = f'repos/{repo}/actions/runs/{run_id}'
    run = api(base)
    jobs = api(base+f'/attempts/{attempt}/jobs?per_page=100')['jobs']
    validate_jobs(run,jobs,sha,run_id,attempt)
    artifacts = api(base+'/artifacts?per_page=100')['artifacts']
    verified = []
    with tempfile.TemporaryDirectory(prefix='ddl-acceptance-') as temporary:
        for name in sorted(REQUIRED):
            if name == 'pg18':
                artifact = 'ddl-pg18-'+sha
                mode = 'pg18'
            else:
                os_name, python = name.removeprefix('offline (').removesuffix(')').split(', ')
                artifact = f'ddl-offline-{os_name}-{python}-{sha}'
                mode = 'offline'
            matches = [a for a in artifacts if a['name']==artifact and not a['expired']]
            if len(matches)!=1:
                raise RuntimeError('BLOCKED_ARTIFACT_MISSING_OR_AMBIGUOUS')
            folder = Path(temporary)/artifact
            subprocess.run(['gh','run','download',run_id,'--repo',repo,'--name',artifact,
                            '--dir',str(folder)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            validate_evidence(folder,mode,sha,run_id,attempt)
            if mode == 'pg18':
                validate_adversarial(folder,sha,run_id,attempt)
            verified.append({'job':name,'artifact_id':matches[0]['id'],'artifact_digest':matches[0].get('digest')})
    (ROOT/'ddl-acceptance.json').write_text(json.dumps({
        'sha':sha,'run_id':run_id,'run_attempt':attempt,'status':'OFFLINE_CI_PASS',
        'physical':'NOT_AUTHORIZED','verified':verified},indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
