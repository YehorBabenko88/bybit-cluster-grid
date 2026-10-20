"""Planning metadata tests only: no providers, network, filesystem discovery."""
import copy,json,pathlib,socket,subprocess
import pytest
from installer.lab_manifest_design import validate_manifest,validate_text
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sample():return json.loads((ROOT/'lab-manifest.example.json').read_text())
def blocked(r):
    assert r['status']=='BLOCKED' and r['physical_deployment']=='NO-GO'
    assert all(r[k] is False for k in ('authorized','readiness','execution_authorized','readiness_passed','physical_ready','schema2_enabled'))
def test_example_is_valid_design_not_evidence():
    r=validate_manifest(sample());assert r['manifest_valid'];blocked(r)
    assert r['native_evidence']=='UNVERIFIED' and r['durable_anti_rollback']=='NOT_IMPLEMENTED'
@pytest.mark.parametrize('flag',['authorized','readiness','execution_authorized','readiness_passed','physical_ready','schema2_enabled'])
@pytest.mark.parametrize('value',[True,0,1,'false',None])
def test_all_top_authority_flags_exact_false(flag,value):
    m=sample();m[flag]=value;r=validate_manifest(m);assert not r['manifest_valid'];blocked(r)
@pytest.mark.parametrize('resource',['host','guests','network','principals','storage','services','trust','time','anti_rollback','retention'])
def test_no_resource_self_attests(resource):
    m=sample();m[resource]['evidence_status']='VERIFIED';assert not validate_manifest(m)['manifest_valid']
@pytest.mark.parametrize('field,value',[
 ('switch_type','EXTERNAL'),('routes',['10.0.0.0/8']),('default_gateway','192.0.2.1'),('tailscale',True),
 ('nat',True),('bridge',True),('internet_access',True),('production_access',True),('dual_homed_guests',True),('clipboard',True)])
def test_isolation_proposals_fail_closed(field,value):
    m=sample();m['network']['proposal'][field]=value;assert not validate_manifest(m)['manifest_valid']
@pytest.mark.parametrize('path',['C:\\ProgramData\\GridLab','L:/GridLab','L:\\GridLab\\..\\GridLab','\\\\server\\GridLab','L:\\GridLab.','L:\\GridLab:ads','l:\\GridLab','L:\\Windows\\GridLab'])
def test_bad_windows_paths(path):
    m=sample();m['storage']['proposal']['parent']=path;assert not validate_manifest(m)['manifest_valid']
@pytest.mark.parametrize('mutation',['duplicate_vm','host_vm_reuse','ls5','sid_reuse','bad_sid','custody_reuse','port_bool','port_reuse','task','service','time_ready','anchor_ready','schema_extra','unknown_field','gate_approval','case_pass','case_missing'])
def test_negative_contracts(mutation):
    m=sample()
    if mutation=='duplicate_vm':m['guests']['proposal'][1]['id']=m['guests']['proposal'][0]['id']
    elif mutation=='host_vm_reuse':m['host']['proposal']['id']=m['guests']['proposal'][0]['id']
    elif mutation=='ls5':m['guests']['proposal'][0]['node_id']='LS5'
    elif mutation=='sid_reuse':
        for p in m['principals']['proposal'][:2]:p['sid']='S-1-5-21-1-2-3-1001'
    elif mutation=='bad_sid':m['principals']['proposal'][0]['sid']='S-1-5-4294967296'
    elif mutation=='custody_reuse':m['principals']['proposal'][1]['custody_domain']=m['principals']['proposal'][0]['custody_domain']
    elif mutation=='port_bool':m['services']['proposal']['postgres_port']=True
    elif mutation=='port_reuse':m['services']['proposal']['postgres_port']=m['services']['proposal']['coordinator_port']
    elif mutation=='task':m['services']['proposal']['registered_tasks']=['Grid']
    elif mutation=='service':m['services']['proposal']['installed_services']=['postgresql']
    elif mutation=='time_ready':m['time']['proposal']['implementation']='IMPLEMENTED'
    elif mutation=='anchor_ready':m['anti_rollback']['proposal']['verified']=True
    elif mutation=='schema_extra':m['storage']['proposal']['schema2_enabled']=True
    elif mutation=='unknown_field':m['host']['proposal']['command']='initdb'
    elif mutation=='gate_approval':m['gates'][2]['authorized']=True
    elif mutation=='case_pass':m['negative_cases'][0]['execution']='PASS'
    else:m['negative_cases'].pop()
    r=validate_manifest(m);assert not r['manifest_valid'];blocked(r)
@pytest.mark.parametrize('text',['{"schema":1,"schema":1}', '{bad}', '['*25+'0'+']'*25, '\ud800', 'NaN', 'x'*65537],ids=['duplicate','malformed','deep','surrogate','nonfinite','oversized'])
def test_corrupt_json_is_fixed_diagnostic(text):
    r=validate_text(text);assert not r['manifest_valid'];blocked(r)
def test_no_live_calls_or_input_mutation(monkeypatch):
    m=sample();saved=copy.deepcopy(m)
    def no(*a,**k):raise AssertionError('LIVE_OPERATION_FORBIDDEN')
    monkeypatch.setattr(subprocess,'Popen',no);monkeypatch.setattr(socket.socket,'connect',no)
    monkeypatch.setattr(pathlib.Path,'stat',no);monkeypatch.setattr(pathlib.Path,'open',no)
    assert validate_manifest(m)['manifest_valid'];assert m==saved

def test_planning_branch_cannot_start_inherited_jobs():
    import re
    for p in (ROOT/'.github/workflows').glob('*.yml'):
        text=p.read_text();jobs=text.split('jobs:\n',1)[1]
        if p.name=='windows-lab-planning.yml':
            assert 'services:' not in text and 'self-hosted' not in text
            continue
        for job in re.split(r'(?m)^  [A-Za-z0-9_-]+:\n',jobs)[1:]:
            first=job.splitlines()[0]
            if p.name=='offline-rc-review.yml':
                assert "github.head_ref == 'review/offline-rc-20261020'" in first
            else:
                assert "github.head_ref != 'planning/windows-lab-l0-20261020'" in first and "github.ref_name != 'planning/windows-lab-l0-20261020'" in first
