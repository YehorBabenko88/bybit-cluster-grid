"""Tests run offline; no Windows providers, ports or PostgreSQL processes."""
import copy
import datetime as dt
import hashlib
import json
import pytest
from installer.isolated_postgres_preflight import assess
from test_isolated_postgres_plan import example

SHA='a'*40
NOW=dt.datetime(2026,10,15,20,0,tzinfo=dt.timezone.utc)
SID='S-1-5-21-100-200-300-1001'

def adapter():
    return dict(root='C:\\GridLab\\'+'a'*32+'_LAB01',run_id='a'*32,node_id='LAB01',
                postgres_port=25432,version=SHA,plan_sha256='b'*64)

def evidence():
    return dict(schema=1,execution_authorized=False,physical_ready=False,commit_sha=SHA,plan_sha256=hashlib.sha256(json.dumps(example(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),status='SNAPSHOT_ONLY',node_id='LAB01',run_id='a'*32,
        data_root=example()['data_root'],captured_at='2026-10-15T20:00:00Z',
        inventory_complete=True,runtime_stopped=True,local_fixed_disk=True,
        path_physical=True,root_absent=True,new_ancestors_absent=True,hardlinks_absent=True,
        postgres_identities_absent=True,tasks_clear=True,ports=[],
        acl=dict(owner_sid=SID,protected=True,writable_sids=[SID,'S-1-5-18','S-1-5-32-544'],sha256='c'*64))

def run(e=None,**kwargs):
    return assess(example(),SHA,mode='PreflightReadOnly',evidence=evidence() if e is None else e,
                  adapter_plan=adapter(),expected_owner_sid=SID,now=NOW,**kwargs)

def test_plan_and_preflight_are_idempotent_but_incompatible_layout_is_blocked():
    p=example();saved=copy.deepcopy(p)
    one=assess(p,SHA,adapter_plan=adapter())
    assert one==assess(p,SHA,adapter_plan=adapter()) and p==saved
    assert one['status']=='PLAN_ONLY' and one['execution_authorized'] is False
    r=run()
    assert r['status']=='BLOCKED' and r['checks']['host_evidence']=='METADATA_ONLY'
    assert 'ADAPTER_LAYOUT_INCOMPATIBLE' in r['blockers']
    assert r['checks']['adapter']=='BLOCKED'
    assert r['ownership']['pgdata']=='ABSENT_UNOWNED'
    assert r['plan_sha256']==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@pytest.mark.parametrize('field,value,code',[
 ('commit_sha','b'*40,'SNAPSHOT_COMMIT_MISMATCH'),('plan_sha256','b'*64,'SNAPSHOT_PLAN_MISMATCH'),
 ('execution_authorized',True,'EVIDENCE_CANNOT_AUTHORIZE_EXECUTION'),('physical_ready',True,'EVIDENCE_CANNOT_AUTHORIZE_EXECUTION'),
 ('inventory_complete',False,'INVENTORY_INCOMPLETE'),('runtime_stopped',False,'RUNTIME_NOT_STOPPED'),
 ('local_fixed_disk',False,'DRIVE_NOT_FIXED_LOCAL'),('path_physical',False,'PATH_REDIRECTED_OR_UNKNOWN'),
 ('root_absent',False,'PGDATA_ALREADY_EXISTS'),('new_ancestors_absent',False,'PREEXISTING_UNOWNED_ANCESTOR'),
 ('hardlinks_absent',False,'HARDLINK_OR_IDENTITY_UNKNOWN'),('postgres_identities_absent',False,'POSTGRES_IDENTITY_PRESENT_OR_UNKNOWN'),
 ('tasks_clear',False,'TASK_REFERENCE_OR_IDENTITY_UNKNOWN'),('node_id','LS5','HOST_IDENTITY_MISMATCH'),
 ('data_root','C:\\other','PATH_IDENTITY_MISMATCH'),('run_id','b'*32,'RUN_ID_MISMATCH'),
 ('captured_at','2026-10-15T19:59:00Z','SNAPSHOT_STALE_OR_INVALID'),
 ('captured_at','2026-10-15T20:00:01Z','SNAPSHOT_STALE_OR_INVALID'),
 ('captured_at','9999999999999999999999','SNAPSHOT_STALE_OR_INVALID'),
 ('ports',[{'transport':'tcp','port':25432}],'PORT_OCCUPIED'),
 ('ports',[{'transport':'udp','port':25432}],'PORT_OCCUPIED'),
 ('ports',[{'transport':'tcp','port':True}],'PORT_INVENTORY_INVALID'),
])
def test_bad_snapshot_never_disappears_behind_layout_blocker(field,value,code):
    e=evidence();e[field]=value;r=run(e)
    assert code in r['blockers'] and r['checks']['host_evidence']=='BLOCKED'
    assert r['physical_ready'] is False

@pytest.mark.parametrize('field,value,code',[
 ('owner_sid','S-1-5-18','ACL_OWNER_MISMATCH'),('protected',False,'ACL_INHERITANCE_UNSAFE'),
 ('writable_sids',['S-1-1-0'],'ACL_UNTRUSTED_WRITER'),('sha256','bad','ACL_EVIDENCE_INVALID')])
def test_unsafe_acl_fails_closed(field,value,code):
    e=evidence();e['acl'][field]=value
    assert code in run(e)['blockers']

def test_duplicate_or_existing_reservation_is_not_a_free_port():
    claim=dict(node_id='LAB01',port=25432,run_id='b'*32)
    assert 'PORT_RESERVATION_CONFLICT' in run(reservations=[claim])['blockers']
    assert 'DUPLICATE_PORT_RESERVATION' in run(reservations=[claim,claim])['blockers']
    r=run(reservations=[])
    assert 'PORT_BIND_NOT_RESERVED' in r['blockers']
    assert r['port_state']=='OBSERVED_ONLY_NOT_RESERVED'

def test_missing_unknown_or_forged_evidence_never_authorizes_execution():
    for e in ({},dict(evidence(),unknown=True),dict(schema=1,status='BLOCKED',code='PG_READ_ONLY_INVENTORY_FAILED')):
        assert run(e)['checks']['host_evidence']=='BLOCKED'
    r=assess(example(),SHA,mode='Apply')
    assert r['status']=='BLOCKED' and 'MODE_UNSUPPORTED' in r['blockers']

def test_planonly_does_not_consume_host_snapshot():
    r=assess(example(),SHA,evidence={'secret':'DO_NOT_LOG'})
    assert 'PLAN_ONLY_EVIDENCE_FORBIDDEN' in r['blockers']
    assert 'DO_NOT_LOG' not in json.dumps(r)

def test_adapter_plan_is_required_and_cannot_silently_rewrite_pgdata():
    r=assess(example(),SHA)
    assert 'ADAPTER_PLAN_REQUIRED' in r['blockers']
    a=adapter();a['root']='C:\\GridLab\\'+'a'*32+'\\LAB01'
    r=assess(example(),SHA,adapter_plan=a)
    assert 'ADAPTER_LAYOUT_INCOMPATIBLE' in r['blockers']


def test_assessment_never_touches_files_processes_or_network(monkeypatch):
    import os
    import socket
    import subprocess
    from pathlib import Path
    def forbidden(*a,**k):
        raise AssertionError('UNEXPECTED_SIDE_EFFECT')
    with monkeypatch.context() as patch:
        patch.setattr(Path,'open',forbidden)
        patch.setattr(os,'mkdir',forbidden)
        patch.setattr(subprocess,'Popen',forbidden)
        patch.setattr(socket.socket,'connect',forbidden)
        assert run()['checks']['host_evidence']=='METADATA_ONLY'


def test_cli_is_readonly_and_emits_exact_identity(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    paths={name:tmp_path/(name+'.json') for name in ('plan','adapter','evidence')}
    e=evidence();e['captured_at']=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for name,data in [('plan',example()),('adapter',adapter()),('evidence',e)]:
        paths[name].write_text(json.dumps(data))
    before={name:path.read_bytes() for name,path in paths.items()}
    command=[sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'installer/isolated_postgres_preflight.py'),
             '--plan',str(paths['plan']),'--commit',SHA,'--adapter-plan',str(paths['adapter'])]
    first=subprocess.run(command,capture_output=True,text=True,check=False)
    assert first.returncode==0 and json.loads(first.stdout)['status']=='PLAN_ONLY'
    second=subprocess.run(command+['--mode','PreflightReadOnly','--owner-sid',SID,'--evidence',str(paths['evidence'])],capture_output=True,text=True,check=False)
    r=json.loads(second.stdout)
    assert second.returncode==2 and r['checks']['host_evidence']=='METADATA_ONLY'
    assert r['commit_sha']==SHA and 'ADAPTER_LAYOUT_INCOMPATIBLE' in r['blockers']
    assert before=={name:path.read_bytes() for name,path in paths.items()}


@pytest.mark.parametrize('bad',['duplicate','json','nan','hardlink'])
def test_bad_input_files_block_without_leaking_contents(tmp_path,bad):
    from installer.isolated_postgres_preflight import read_json
    p=tmp_path/'plan.json'
    if bad=='duplicate':p.write_text('{"schema":1,"schema":1,"secret":"PRIVATE"}')
    elif bad=='json':p.write_text('{broken PRIVATE')
    elif bad=='nan':p.write_text('{"schema":NaN}')
    else:
        p.write_text(json.dumps(example()))
        (tmp_path/'alias.json').hardlink_to(p)
    with pytest.raises((ValueError,RuntimeError)):
        read_json(p)
