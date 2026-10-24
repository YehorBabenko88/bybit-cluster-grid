import copy
import hashlib
import json
from pathlib import Path
import pytest
from tools.check_ddl_acceptance import REQUIRED, validate_jobs, validate_evidence


def fixture():
    run = {'id':42,'head_sha':'a'*40,'run_attempt':2}
    jobs = [dict(run_id=42,head_sha='a'*40,run_attempt=2,name=n,status='completed',conclusion='success') for n in REQUIRED]
    return run,jobs


def test_complete_exact_attempt_passes():
    run,jobs=fixture()
    validate_jobs(run,jobs,'a'*40,42,2)


@pytest.mark.parametrize('mutation', ['skip','missing','duplicate','old-attempt','wrong-sha','running','failure','wrong-run'])
def test_fail_closed_inventory(mutation):
    run,jobs=copy.deepcopy(fixture())
    if mutation=='skip': jobs[0]['conclusion']='skipped'
    if mutation=='missing': jobs.pop()
    if mutation=='duplicate': jobs.append(jobs[0])
    if mutation=='old-attempt': jobs[0]['run_attempt']=1
    if mutation=='wrong-sha': jobs[0]['head_sha']='b'*40
    if mutation=='running': jobs[0]['status']='in_progress'
    if mutation=='failure': jobs[0]['conclusion']='failure'
    if mutation=='wrong-run': run['id']=43
    with pytest.raises(RuntimeError,match='BLOCKED'):
        validate_jobs(run,jobs,'a'*40,42,2)


def test_missing_artifacts_blocked(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_evidence(tmp_path,'pg18','a'*40,42,2)


@pytest.mark.parametrize('mutation',['clean','attempt','junit-skip','inventory','hash','missing-hash'])
def test_downloaded_evidence_is_not_trusted(tmp_path, monkeypatch, mutation):
    from tools import check_ddl_acceptance as gate
    monkeypatch.setattr(gate,'ROOT',tmp_path)
    monkeypatch.setattr(gate.subprocess,'check_output',lambda *a,**k:b'')
    fixtures=tmp_path/'tests/fixtures';fixtures.mkdir(parents=True)
    inv={'nodes':['test.py::test_ok'],'junit_cases':[['test','test_ok']]}
    (fixtures/'ddl_offline_inventory.json').write_text(json.dumps(inv))
    events={'sha':'a'*40,'run_id':42,'run_attempt':2,'collected':inv['nodes'],'passed':inv['nodes'],'bad':[]}
    if mutation=='inventory': events['passed']=[]
    if mutation=='attempt': events['run_attempt']=1
    (tmp_path/'ddl-offline-events.json').write_text(json.dumps(events))
    skipped='1' if mutation=='junit-skip' else '0'
    (tmp_path/'ddl-offline.xml').write_text(f'<testsuites><testsuite skipped="{skipped}"><testcase classname="test" name="test_ok"/></testsuite></testsuites>')
    (tmp_path/'ddl-dependencies.txt').write_text('synthetic==1\n')
    files={n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in
           ('ddl-offline.xml','ddl-offline-events.json','ddl-dependencies.txt')}
    if mutation=='hash': files['ddl-offline.xml']='0'*64
    if mutation=='missing-hash': files.pop('ddl-dependencies.txt')
    (tmp_path/'ddl-offline-sha256.json').write_text(json.dumps({
        'sha':'a'*40,'run_id':42,'run_attempt':2,'files':files}))
    if mutation=='clean':
        validate_evidence(tmp_path,'offline','a'*40,42,2)
    else:
        with pytest.raises(RuntimeError,match='BLOCKED'):
            validate_evidence(tmp_path,'offline','a'*40,42,2)


def test_branch_rename_cannot_skip_required_gates():
    root=Path(__file__).resolve().parents[1]
    text=(root/'.github/workflows/ddl-free-runtime.yml').read_text()
    assert text.count("(github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch')")==2
    assert 'needs: [offline, pg18]' in text
    assert 'always() &&' in text
    assert "test \"$PG18_RESULT\" = success" in text


@pytest.mark.parametrize('mutation',['clean','empty-hashes','wrong-baseline','phase-label','missing-events','bad-inventory'])
def test_adversarial_receipt_is_fail_closed(tmp_path, monkeypatch, mutation):
    from tools import check_ddl_acceptance as gate
    cases=json.loads((gate.ROOT/'tests/fixtures/pr227_adversarial_inventory.json').read_text())
    sources={'grid/schema_contract.py','tools/check_ddl_free_ci.py',
             'tests/test_pr227_adversarial_pg18.py','tools/check_pr227_adversarial_ci.py'}
    monkeypatch.setattr(gate.subprocess,'check_output',lambda *a,**k:b'synthetic-source')
    audit={'sha':'a'*40,'run_id':42,'run_attempt':2,
           'baseline':'da69209af86567232fb3038a899580fe2e061a0b','files':{},'results':{}}
    for source in sources: audit['files'][source]=hashlib.sha256(b'synthetic-source').hexdigest()
    for phase,acceptance in [('baseline-vulnerability-reproduced',False),('candidate-rejection',True)]:
        prefix='pr227-'+phase
        audit['results'][phase]={'tests':len(cases),'security_acceptance':acceptance}
        (tmp_path/(prefix+'.xml')).write_text('<testsuites><testsuite>'+''.join(
            f'<testcase name="{n}"/>' for n in cases)+'</testsuite></testsuites>')
        nodes=['test.py::'+n for n in cases]
        (tmp_path/(prefix+'-events.json')).write_text(json.dumps({'nodes':nodes,'passed':nodes,'bad':[]}))
        for suffix in ('.xml','-events.json'):
            path=tmp_path/(prefix+suffix);audit['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    if mutation=='empty-hashes': audit['files']={}
    if mutation=='wrong-baseline': audit['baseline']='b'*40
    if mutation=='phase-label': audit['results']['baseline-vulnerability-reproduced']['security_acceptance']=True
    if mutation=='missing-events': (tmp_path/'pr227-candidate-rejection-events.json').unlink()
    if mutation=='bad-inventory': (tmp_path/'pr227-candidate-rejection-events.json').write_text(json.dumps({'nodes':[],'passed':[],'bad':[]}))
    (tmp_path/'pr227-audit-sha256.json').write_text(json.dumps(audit))
    if mutation=='clean': gate.validate_adversarial(tmp_path,'a'*40,42,2)
    else:
        with pytest.raises((RuntimeError,FileNotFoundError)):
            gate.validate_adversarial(tmp_path,'a'*40,42,2)
