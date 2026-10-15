import copy,json
from pathlib import Path, PureWindowsPath
import pytest
from installer import physical_deployment_harness as h
SHA='a'*40
from installer.tests.physical_harness_fixture import fleet, RUN
@pytest.mark.parametrize('n',[1,2,5])
def test_sequence_never_authorizes_execution(n):
    data=fleet(n);before=copy.deepcopy(data)
    r=h.plan(data,SHA)
    assert r['status']=='PLAN_ONLY' and r['execution_authorized'] is False and r['physical_ready'] is False
    assert r['sequence'][0]['nodes']==['LAB0']
    assert all(x['operator_approval_required'] for x in r['sequence'])
    assert len(r['scenarios'])==8
    assert all(x['physical_status']=='REQUIRES_OPERATOR_APPROVAL' for x in r['scenarios'])
    assert all(x['database']['new_cluster_required'] for x in r['nodes'])
    assert all(x['database']['port'] not in [55432,55433,5432] for x in r['nodes'])
    assert data==before and r==h.plan(data,SHA)
@pytest.mark.parametrize('field,value',[('id','LS5'),('id','LS7'),('runtime_stopped',False),('inventory_complete',False),
 ('test_root_exists',True),('test_root',r'C:\ProgramData\GridLab'),('test_root',r'\\server\share'),
 ('cpu_logical',True),('cpu_logical',1),('ram_bytes',1),('disk_free_bytes',1),('python_version','3.10.9'),
 ('postgres_major',15),('ssh_available',False),('tailscale_available',False),('address','localhost;shutdown'),
 ('address','127.0.0.1'),('role','PILOT'),('test_root',r'C:\GridLab\..\owned')])
def test_bad_node_stops_entire_sequence(field,value):
    f=fleet();f['nodes'][0][field]=value
    r=h.plan(f,SHA)
    assert r['status']=='BLOCKED' and r['sequence']==[] and r['execution_authorized'] is False
@pytest.mark.parametrize('damage',['duplicate-id','duplicate-address','two-control','no-control','bad-run','wrong-root-run','unknown-field'])
def test_ambiguous_fleet_is_blocked(damage):
    f=fleet()
    if damage=='duplicate-id':f['nodes'][1]['id']=f['nodes'][0]['id'].lower()
    if damage=='duplicate-address':f['nodes'][1]['address']=f['nodes'][0]['address']
    if damage=='two-control':f['nodes'][1]['role']='CONTROL'
    if damage=='no-control':f['nodes'][0]['role']='WORKER'
    if damage=='bad-run':f['run_id']='../outside'
    if damage=='wrong-root-run':f['nodes'][0]['test_root']=r'C:\GridLab\other\LAB0'
    if damage=='unknown-field':f['apply']=True
    assert h.plan(f,SHA)['status']=='BLOCKED'
def junit(skipped=False,failed=False,missing=False):
    from xml.etree.ElementTree import Element,SubElement,tostring
    root=Element('testsuites');suite=SubElement(root,'testsuite')
    entries=list(h.SCENARIOS.items())
    for scenario,spec in entries[:-1] if missing else entries:
        for selector in spec['selectors']:
            file,name=selector.split('::',1)
            t=SubElement(suite,'testcase',classname=file[:-3].replace('/','.'),name=name)
            if skipped:SubElement(t,'skipped')
            if failed:SubElement(t,'failure')
    return tostring(root)
@pytest.mark.parametrize('damage',['skip','fail','missing','empty','xml','dtd'])
def test_results_do_not_invent_pass(damage):
    raw=junit(skipped=damage=='skip',failed=damage=='fail',missing=damage=='missing')
    if damage=='empty':raw=b'<testsuites/>'
    if damage=='xml':raw=b'<broken'
    if damage=='dtd':raw=b'<!DOCTYPE x><testsuites/>'
    r=h.results(raw,SHA,'12345')
    assert r['status']=='BLOCKED' and r['physical_ready'] is False
def test_real_test_evidence_is_synthetic_only():
    r=h.results(junit(),SHA,'12345')
    assert r['status']=='SYNTHETIC_PASS' and r['commit_sha']==SHA and r['workflow_run_id']=='12345'
    assert all(s['physical_status']=='NOT_RUN' for s in r['scenarios'])
    assert all(s['case_ids'] for s in r['scenarios'])

@pytest.mark.parametrize('damage',['utf16-dtd','false-counters'])
def test_forged_junit_is_not_evidence(damage):
    raw=junit()
    if damage=='utf16-dtd':raw=('<?xml version="1.0" encoding="utf-16"?><!DOCTYPE testsuites>'+raw.decode()).encode('utf-16')
    if damage=='false-counters':raw=raw.replace(b'<testsuite>',b'<testsuite failures="1">')
    assert h.results(raw,SHA,'12345')['status']=='BLOCKED'
