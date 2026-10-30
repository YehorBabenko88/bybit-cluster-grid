"""Synthetic GitHub metadata only; no API calls in these unit cases."""
import copy
import pytest
from integration.pr_compatibility import PRS,REQUIRED_WORKFLOWS,compare

def fixture():
    return dict(schema=1,prs=[dict(pr=n,head=str(n%10)*40,files={'grid/coordinator.py':dict(sha256='a'*64,interface_sha256='b'*64)},changed_files=['grid/coordinator.py'],complete=True,ci=[dict(name=w,head=str(n%10)*40,run_id=100+i,status='completed',conclusion='success',artifact_count=1) for i,w in enumerate(REQUIRED_WORKFLOWS[n])]) for n in PRS])

def test_consistent_sources_and_green_metadata_are_not_acceptance():
    r=compare(fixture(),fixture())
    assert r['metadata_valid'] and r['ci_all_success'] and not r['head_drift']
    assert r['g1']=='BLOCKED' and not r['physical_ready'] and not r['artifact_bytes_verified']

@pytest.mark.parametrize('state',['queued','in_progress','pending','waiting','failure','skipped','cancelled','timed_out'])
def test_non_success_or_skipped_never_passes(state):
    x=fixture();x['prs'][0]['ci'][0].update(status=state,conclusion=state)
    assert not compare(x,fixture())['ci_all_success']

def test_changed_head_and_shared_source_identifies_owner():
    x=fixture();x['prs'][0]['head']='f'*40;x['prs'][0]['files']['grid/coordinator.py']['sha256']='c'*64
    r=compare(x,fixture())
    assert r['head_drift']==[238] and r['overlaps'][0]['divergent']
    assert 'SCHEMA_OR_RUNTIME_REVIEW' in r['overlaps'][0]['review']

@pytest.mark.parametrize('mutation',['missing_pr','duplicate_pr','missing_ci','wrong_head','no_artifact','partial','false_count','bad_path','missing_file','newer_queued'])
def test_unknown_or_truncated_metadata_blocks(mutation):
    x=fixture();p=x['prs'][0]
    if mutation=='missing_pr':x['prs'].pop()
    if mutation=='duplicate_pr':x['prs'][-1]=copy.deepcopy(p)
    if mutation=='missing_ci':p['ci']=[]
    if mutation=='wrong_head':p['ci'][0]['head']='f'*40
    if mutation=='no_artifact':p['ci'][0]['artifact_count']=0
    if mutation=='partial':p['complete']=False
    if mutation=='false_count':p['ci'][0]['artifact_count']=True
    if mutation=='bad_path':p['files']['../unsafe']=p['files'].pop('grid/coordinator.py')
    if mutation=='missing_file':p['files']['grid/coordinator.py']=None
    if mutation=='newer_queued':p['ci'].append(dict(p['ci'][0],run_id=999,status='queued',conclusion=None))
    r=compare(x,fixture())
    assert not r['metadata_valid'] or not r['ci_all_success']
    assert r['g1']=='BLOCKED'


def test_duplicate_json_keys_and_nonfinite_are_rejected():
    from integration.pr_compatibility import strict_metadata
    for raw in ('{"schema":1,"schema":1}', '{"value":NaN}'):
        with pytest.raises(ValueError):strict_metadata(raw)

def test_no_args_cli_is_plan_only_without_github_access():
    import subprocess,sys,json
    r=subprocess.run([sys.executable,'-m','integration.pr_compatibility'],capture_output=True,text=True,timeout=10)
    assert r.returncode==0 and json.loads(r.stdout)['network_calls']==0
