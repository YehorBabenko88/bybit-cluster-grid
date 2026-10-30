"""Independent maintenance contracts: an offline result can never authorize a host."""
import copy
import json
import uuid
from pathlib import Path

import pytest
from tools import grid_physical_maintenance as m


def snapshot():
    return dict(schema='grid-maintenance-1',head='a'*40,tree='b'*40,run_id=str(uuid.uuid4()),
                node='LS5',scope='SYNTHETIC_OFFLINE',observed_utc='2026-10-30T18:00:00Z',
                checks={key:dict(status='PASS',reason='SYNTHETIC_COMPLETE',data=[]) for key in m.GATES},
                execute=False,cleanup=False,deployment='NO-GO')


def test_complete_model_is_never_physical_acceptance():
    s=snapshot();r=m.evaluate(s,s['head'],s['tree'],s['run_id'],'LS5')
    assert r['model']=='OFFLINE_MODEL_PASS'
    assert r['physical']=='BLOCKED' and r['execute'] is False and r['cleanup'] is False
    assert all(x['argv'] is None for x in m.stage_plan(s['head'],s['run_id'],'LS5')['stages'] if x['mutates'])


@pytest.mark.parametrize('gate',sorted(m.GATES))
@pytest.mark.parametrize('status',['FAIL','BLOCKED','UNKNOWN',None,True,1,'SKIPPED'])
def test_missing_failed_or_unknown_gate_cannot_pass(gate,status):
    s=snapshot();s['checks'][gate]['status']=status
    assert m.evaluate(s,s['head'],s['tree'],s['run_id'],'LS5')['model']=='BLOCKED'


@pytest.mark.parametrize('key,value',[('head','c'*40),('tree','c'*40),('run_id',str(uuid.uuid4())),('node','PC4'),('execute',True),('cleanup',1),('deployment','GO'),('schema',True)],ids=['head','tree','run_id','node','execute','cleanup','deployment','schema'])
def test_context_or_authority_substitution_is_blocked(key,value):
    s=snapshot();old=copy.deepcopy(s);s[key]=value
    assert m.evaluate(s,old['head'],old['tree'],old['run_id'],'LS5')['model']=='BLOCKED'


def test_omitted_gate_or_unknown_field_is_blocked():
    s=snapshot();del s['checks']['token'];assert m.evaluate(s,s['head'],s['tree'],s['run_id'],'LS5')['model']=='BLOCKED'
    s=snapshot();s['password']='secret';r=m.evaluate(s,s['head'],s['tree'],s['run_id'],'LS5');assert 'secret' not in json.dumps(r) and r['model']=='BLOCKED'


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'['*10000,b'\xff',b'{}'*600000],ids=['duplicate','nonfinite','deep','encoding','oversize'])
def test_strict_json_rejects_ambiguous_or_unbounded_data(raw):
    with pytest.raises(ValueError):m.strict_json(raw)


def test_host_observation_is_not_an_authenticated_statement():
    s=snapshot();s['scope']='UNATTESTED_READ_ONLY';r=m.evaluate(s,s['head'],s['tree'],s['run_id'],'LS5')
    assert r['physical']=='BLOCKED' and r['model']=='OFFLINE_MODEL_PASS'


@pytest.mark.parametrize('action',['Stage','Prepare','Execute','Cleanup','FirewallApply','PostgresDrop'])
def test_plan_has_no_executable_mutation_even_with_forged_approval(action):
    p=m.stage_plan('a'*40,str(uuid.uuid4()),'PC4')
    assert p['authorization']=='NOT_AUTHORIZED' and p['deployment']=='NO-GO'
    assert all(s['argv'] is None for s in p['stages'] if s['mutates'])
    assert 'password' not in json.dumps(p).lower()


def test_junit_skips_xfail_empty_inventory_or_replay_is_not_success():
    for raw in [b'<testsuite tests="0"/>',b'<testsuite tests="1" failures="0" errors="0" skipped="1"><testcase name="a"><skipped/></testcase></testsuite>',b'<!DOCTYPE x><testsuite/>']:
        with pytest.raises(ValueError):m.verify_junit(raw,{'a'})
    raw=b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="a"/></testsuite>'
    assert m.verify_junit(raw,{'a'})==1
    with pytest.raises(ValueError):m.verify_junit(raw,{'other'})


def test_existing_s0_verifier_is_required_not_reimplemented():
    assert m.verify_s0.__module__=='tools.s0_independent_acceptance'

def test_independent_ci_digest_context_and_sources_are_external():
    import io,zipfile,hashlib
    expected=dict(head='a'*40,tree='b'*40,run_id='123',attempt='1');pins={'installer/maintenance/GridMaintenance.ps1':'c'*64}
    xml=b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="a"/></testsuite>'
    files={'tests.xml':xml,'python.jsonl':b'{"name":"a","status":"TEST_PASS"}\n'}
    record=dict(expected,scope='OFFLINE_OR_HOSTED_NOT_PHYSICAL',mode='offline',execute=False,cleanup=False,deployment='NO-GO',sources=pins,files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for k,v in files.items():archive.writestr(k,v)
        archive.writestr('manifest-offline.json',json.dumps(record))
    raw=stream.getvalue();sha=hashlib.sha256(raw).hexdigest()
    assert m.verify_ci_zip(raw,sha,expected,pins,'offline',{'a'})['physical']=='BLOCKED'
    for wrong in (dict(expected,head='d'*40),dict(expected,run_id='124'),dict(expected,attempt='2')):
        with pytest.raises(ValueError):m.verify_ci_zip(raw,sha,wrong,pins,'offline',{'a'})
    with pytest.raises(ValueError):m.verify_ci_zip(raw,'0'*64,expected,pins,'offline',{'a'})
    with pytest.raises(ValueError):m.verify_ci_zip(raw,sha,expected,{'x':'f'*64},'offline',{'a'})

    with pytest.raises(ValueError):m.verify_ci_zip(raw,sha,expected,pins,'offline',{'a','missing_test'})

def test_mocked_payload_cannot_be_blocked_with_forged_success_junit():
    import io,zipfile,hashlib
    from tools.grid_maintenance_ci import PS_NAMES
    expected=dict(head='a'*40,tree='b'*40,run_id='123',attempt='1');pins={'p':'c'*64}
    names=sorted(PS_NAMES)
    xml=('<testsuite tests="'+str(len(names))+'" errors="0" failures="0" skipped="0">'+''.join('<testcase name="'+name+'"/>' for name in names)+'</testsuite>').encode()
    mocked=dict(scope='SYNTHETIC_OFFLINE_NOT_PHYSICAL',status='BLOCKED',cases=len(names),names=names,execute=False,cleanup=False)
    files={'powershell.xml':xml,'powershell.json':json.dumps(mocked).encode()}
    record=dict(expected,scope='OFFLINE_OR_HOSTED_NOT_PHYSICAL',mode='mocked',execute=False,cleanup=False,deployment='NO-GO',sources=pins,files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for k,v in files.items():z.writestr(k,v)
        z.writestr('manifest-mocked.json',json.dumps(record))
    raw=out.getvalue()
    with pytest.raises(ValueError):m.verify_ci_zip(raw,hashlib.sha256(raw).hexdigest(),expected,pins,'mocked',set())


def test_formal_schema_rejects_extra_properties_and_unknown_states():
    import jsonschema
    schema=json.loads((Path(__file__).resolve().parents[2]/'installer/maintenance/snapshot.schema.json').read_text())
    s=snapshot();jsonschema.validate(s,schema)
    s['checks']['token']['status']='UNKNOWN'
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(s,schema)
    s=snapshot();s['approval']=True
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(s,schema)
