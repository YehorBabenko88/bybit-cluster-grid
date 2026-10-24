"""Offline contracts only. No host, network, database or native security calls."""
import datetime as dt
import pytest
from integration.physical_program import CHECKS,make_profile,validate_profile,assess_snapshots

HEAD='a'*40
RUN='b'*32
NOW=dt.datetime(2026,10,24,10,tzinfo=dt.timezone.utc)

def snapshot(node):
    return dict(schema='grid-g0-observation-1',node=node,head=HEAD,run_id=RUN,
        host_id=('1' if node=='LS5' else '2')*64,observed_utc=NOW.isoformat(),
        observation_kind='UNATTESTED_READ_ONLY',g1_authorized=False,g2_authorized=False,
        checks={k:dict(status='PASS',reason='OBSERVED',data=[]) for k in CHECKS})

def test_valid_profile_is_plan_only_not_execution():
    p=make_profile(HEAD,RUN)
    r=validate_profile(p)
    assert r['status']=='OFFLINE_MODEL_PASS' and r['g1']=='BLOCKED' and not r['host_verified']

@pytest.mark.parametrize('field',['execute','cleanup','deployment','production_database','schema2'])
def test_authority_cannot_be_enabled(field):
    p=make_profile(HEAD,RUN);p['permissions'][field]=True
    assert validate_profile(p)['status']=='BLOCKED'

@pytest.mark.parametrize('port',[5432,55432,55433,8765,22,True,0,65536])
def test_reserved_or_invalid_ports_blocked(port):
    p=make_profile(HEAD,RUN);p['ports']['postgres']=port
    assert validate_profile(p)['status']=='BLOCKED'

@pytest.mark.parametrize('root',[r'C:\ProgramData\Grid',r'C:\GridLab\FirstBoot\..\PC4',r'\\server\share',r'C:\GridLab\FirstBoot'+'\\'+RUN+r'\LS5:stream',r'C:\GridLab\FirstBoot'+'\\'+RUN+r'\ls5'])
def test_path_alias_and_production_roots_blocked(root):
    p=make_profile(HEAD,RUN);p['nodes']['LS5']['root']=root
    assert validate_profile(p)['status']=='BLOCKED'

@pytest.mark.parametrize('change',[dict(api_bind='0.0.0.0'),dict(postgres_instance='existing'),dict(network_isolation='python_audit_hook')])
def test_inadequate_isolation_blocked(change):
    p=make_profile(HEAD,RUN);p['isolation'].update(change)
    assert validate_profile(p)['status']=='BLOCKED'

def test_duplicate_ports_and_external_market_blocked():
    p=make_profile(HEAD,RUN);p['ports']['synthetic']=p['ports']['api']
    assert validate_profile(p)['status']=='BLOCKED'
    p=make_profile(HEAD,RUN);p['market']='https://api.bybit.com'
    assert validate_profile(p)['status']=='BLOCKED'

def test_complete_self_report_does_not_attest_host_or_authorize_g1():
    r=assess_snapshots(make_profile(HEAD,RUN),[snapshot('LS5'),snapshot('PC4')],NOW)
    assert r['offline_valid'] and r['g0']=='BLOCKED' and r['g1']=='BLOCKED'
    assert not r['host_verified'] and 'INDEPENDENT_G0_REVIEW_REQUIRED' in r['blocked']

@pytest.mark.parametrize('mutation',['head','run_id','host_alias','stale','future','missing','unknown','secret','forged_authority'])
def test_snapshot_corruption_or_unknown_never_ready(mutation):
    s=snapshot('PC4')
    if mutation=='head':s['head']='c'*40
    if mutation=='run_id':s['run_id']='c'*32
    if mutation=='host_alias':s['host_id']='1'*64
    if mutation=='stale':s['observed_utc']=(NOW-dt.timedelta(hours=1)).isoformat()
    if mutation=='future':s['observed_utc']=(NOW+dt.timedelta(minutes=1)).isoformat()
    if mutation=='missing':del s['checks']['processes']
    if mutation=='unknown':s['checks']['acl']['status']='UNKNOWN'
    if mutation=='secret':s['checks']['processes']['data']=[dict(CommandLine='private-secret')]
    if mutation=='forged_authority':s['g1_authorized']=True
    r=assess_snapshots(make_profile(HEAD,RUN),[snapshot('LS5'),s],NOW)
    assert not r['offline_valid'] and r['g0']=='BLOCKED' and 'private-secret' not in str(r)

def test_failed_gate_is_no_go_and_missing_host_is_blocked():
    s=snapshot('LS5');s['checks']['paths']['status']='FAIL'
    assert assess_snapshots(make_profile(HEAD,RUN),[s,snapshot('PC4')],NOW)['g0']=='NO-GO'
    assert assess_snapshots(make_profile(HEAD,RUN),[s],NOW)['g0']=='BLOCKED'


def test_port_conflict_and_existing_planned_root_are_no_go():
    p=make_profile(HEAD,RUN);s=snapshot('LS5')
    s['checks']['listeners']['data']=[dict(port=p['ports']['api'],address='127.0.0.1',pid=123)]
    assert assess_snapshots(p,[s,snapshot('PC4')],NOW)['g0']=='NO-GO'
    s=snapshot('LS5');s['checks']['paths']['data']=[dict(path=p['nodes']['LS5']['root'],exists=True,reparse=False)]
    assert assess_snapshots(p,[s,snapshot('PC4')],NOW)['g0']=='NO-GO'

@pytest.mark.parametrize('data',[dict(name='POSTGRES_DSN=private'),dict(name='PRIVATE_SECRET_NAME')])
def test_only_allowlisted_environment_names_accepted(data):
    s=snapshot('LS5');s['checks']['environment']['data']=[data]
    assert not assess_snapshots(make_profile(HEAD,RUN),[s,snapshot('PC4')],NOW)['offline_valid']


def test_formal_profile_and_snapshot_schemas_match_offline_contract():
    import json
    from pathlib import Path
    import jsonschema
    root=Path(__file__).resolve().parents[1]/'planning'/'physical-first-boot'
    profile_schema=json.loads((root/'profile.schema.json').read_text())
    observation_schema=json.loads((root/'g0-observation.schema.json').read_text())
    jsonschema.Draft202012Validator.check_schema(profile_schema)
    jsonschema.Draft202012Validator.check_schema(observation_schema)
    jsonschema.validate(make_profile(HEAD,RUN),profile_schema)
    jsonschema.validate(snapshot('LS5'),observation_schema)
    bad=snapshot('LS5');bad['checks']['processes']['data']=[{'CommandLine':'private'}]
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,observation_schema)


def test_g1_evidence_plan_cannot_claim_actual_execution():
    import json
    from pathlib import Path
    import jsonschema
    root=Path(__file__).resolve().parents[1]/'planning'/'physical-first-boot'
    schema=json.loads((root/'g1-evidence.schema.json').read_text())
    example=json.loads((root/'g1-evidence.example.json').read_text())
    jsonschema.validate(example,schema)
    example['phases'][0]['status']='PASS'
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(example,schema)
