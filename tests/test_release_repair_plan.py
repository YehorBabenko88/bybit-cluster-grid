"""Read-only assessment contracts. No live DB/OS providers or target imports."""
import hashlib,json,socket,subprocess
from pathlib import Path
import pytest
from installer.tests.release_repair_fixture import make_fixture,LEGACY,REVIEWED,PREVIOUS
from installer import release_repair_plan as p

def snapshot(root):
    return {f.relative_to(root).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}

@pytest.mark.parametrize('phase',['prepared','committed','none'])
@pytest.mark.parametrize('schema',[47,48])
@pytest.mark.parametrize('role',['CONTROL','WORKER'])
@pytest.mark.parametrize('legacy',[LEGACY,'2017ed4fd16b0b222173a6d42b5bf24b2beb73ac'])
def test_plan_is_deterministic_and_never_authorizes_repair(tmp_path,phase,schema,role,legacy,monkeypatch):
    make_fixture(tmp_path,phase,role,schema,legacy)
    before=snapshot(tmp_path)
    def forbidden(*a,**k):raise AssertionError('network/subprocess forbidden')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(subprocess,'run',forbidden)
    a=p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json',role)
    assert a==p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json',role)
    assert a['status']=='PLAN_ONLY' and a['observed_schema']==schema
    assert a['activation_authorized'] is False and a['repair_authorized'] is False
    assert a['marker_removal_authorized'] is False and a['proposed_changes']==[]
    assert a['legacy_rollback_compatible']==(schema==47)
    assert a['journal_target']==(PREVIOUS if phase=='prepared' else legacy)
    assert a['database_checked_live'] is False
    assert snapshot(tmp_path)==before

@pytest.mark.parametrize('damage',['json','duplicate','bool-schema','phase','foreign-current','foreign-pending','previous',
    'missing-current','missing-manifest','corrupt-manifest','uncovered-python','candidate-unfenced','candidate-schema47',
    'evidence-schema49','evidence-active','evidence-release','evidence-unchecked','evidence-activation','evidence-blocked',
    'failed-reviewed','directory-pointer','unknown-historical'])
def test_ambiguous_or_damaged_evidence_blocks_without_changes(tmp_path,damage):
    make_fixture(tmp_path)
    jp=tmp_path/'switch-journal.json';ep=tmp_path/'schema-evidence.json'
    j=json.loads(jp.read_text());e=json.loads(ep.read_text())
    if damage=='json':jp.write_text('{broken')
    if damage=='duplicate':jp.write_text(jp.read_text()[:-1]+',"schema":1}')
    if damage=='bool-schema':j['schema']=True;jp.write_text(json.dumps(j))
    if damage=='phase':j['phase']='unknown';jp.write_text(json.dumps(j))
    if damage=='foreign-current':(tmp_path/'current.version').write_text('c'*40)
    if damage=='foreign-pending':(tmp_path/'pending.version').write_text('c'*40)
    if damage=='previous':(tmp_path/'previous.version').write_text('c'*40)
    if damage=='missing-current':(tmp_path/'current.version').unlink()
    if damage=='missing-manifest':(tmp_path/'releases'/LEGACY/'release-manifest.json').unlink()
    if damage=='corrupt-manifest':(tmp_path/'releases'/LEGACY/'grid/db.py').write_text('corrupt')
    if damage=='uncovered-python':(tmp_path/'releases'/LEGACY/'extra.py').write_text('pass')
    if damage=='candidate-unfenced':(tmp_path/'releases'/REVIEWED/'grid/control_runtime.py').unlink()
    if damage=='candidate-schema47':(tmp_path/'releases'/REVIEWED/'grid/migrations.py').write_text('MIGRATIONS=[]')
    if damage=='evidence-schema49':e['checks']['database']['migration']=49
    if damage=='evidence-active':e['checks']['database']['runtime_state']='ACTIVE'
    if damage=='evidence-release':e['checks']['release']['version']='c'*40
    if damage=='evidence-unchecked':e['database_checked']=False
    if damage=='evidence-activation':e['activation_authorized']=True
    if damage=='evidence-blocked':e['status']='BLOCKED'
    if damage.startswith('evidence-'):ep.write_text(json.dumps(e))
    if damage=='failed-reviewed':(tmp_path/'failed.version').write_text(REVIEWED)
    if damage=='directory-pointer':(tmp_path/'pending.version').unlink();(tmp_path/'pending.version').mkdir()
    if damage=='unknown-historical':
        old=tmp_path/'releases'/LEGACY;new=tmp_path/'releases'/('c'*40);old.rename(new)
        j['candidate']='c'*40;jp.write_text(json.dumps(j));(tmp_path/'current.version').write_text('c'*40);(tmp_path/'pending.version').write_text('c'*40)
    before=snapshot(tmp_path)
    result=p.assess(tmp_path,REVIEWED,ep,'CONTROL')
    assert result['status']=='BLOCKED'
    assert result['activation_authorized'] is False and result['repair_authorized'] is False
    assert snapshot(tmp_path)==before

def test_after_prepared_recovery_no_pending_is_only_an_assessment(tmp_path):
    make_fixture(tmp_path,'none')
    (tmp_path/'pending.version').unlink();(tmp_path/'current.version').write_text(PREVIOUS)
    a=p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json','CONTROL')
    assert a['status']=='PLAN_ONLY' and a['transaction_state']=='NO_PENDING_TRANSACTION'
    assert a['repair_authorized'] is False

def test_redacted_cli_rejection(tmp_path,capsys):
    ep=tmp_path/'evidence.json';ep.write_text('postgresql://user:SECRET@localhost/db')
    assert p.main(['--install-root',str(tmp_path),'--reviewed-version',REVIEWED,'--schema-evidence',str(ep)])==2
    assert 'SECRET' not in capsys.readouterr().out


@pytest.mark.parametrize('current',[PREVIOUS,LEGACY])
@pytest.mark.parametrize('pending',[None,LEGACY])
@pytest.mark.parametrize('previous',[None,PREVIOUS])
def test_prepared_partial_write_boundaries_are_assessed_only(tmp_path,current,pending,previous):
    make_fixture(tmp_path,'prepared')
    (tmp_path/'current.version').write_text(current)
    for name,value in [('pending',pending),('previous',previous)]:
        file=tmp_path/(name+'.version')
        if value is None:file.unlink()
        else:file.write_text(value)
    before=snapshot(tmp_path)
    result=p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json')
    assert result['status']=='PLAN_ONLY' and result['journal_target']==PREVIOUS
    assert result['repair_authorized'] is False and snapshot(tmp_path)==before


def test_correctly_rehashed_but_unknown_candidate_catalogue_is_rejected(tmp_path):
    make_fixture(tmp_path)
    root=tmp_path/'releases'/REVIEWED
    (root/'grid/migrations.py').write_text('MIGRATIONS=[]')
    mp=root/'release-manifest.json';data=json.loads(mp.read_text())
    data['files']['grid/migrations.py']=hashlib.sha256((root/'grid/migrations.py').read_bytes()).hexdigest()
    mp.write_text(json.dumps(data))
    assert p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json')['code']=='REPAIR_CANDIDATE_CATALOGUE_UNREVIEWED'


def test_changed_marker_during_assessment_fails_closed(tmp_path,monkeypatch):
    make_fixture(tmp_path)
    original=p.read_file
    def read(path,*args,**kwargs):
        value=original(path,*args,**kwargs)
        if path==tmp_path/'releases'/REVIEWED/'grid/migrations.py':
            (tmp_path/'current.version').write_text(PREVIOUS)
        return value
    monkeypatch.setattr(p,'read_file',read)
    assert p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json')['code']=='REPAIR_EVIDENCE_CHANGED'


def test_redirected_evidence_is_rejected(tmp_path,monkeypatch):
    make_fixture(tmp_path)
    original=p.w.physical
    monkeypatch.setattr(p.w,'physical',lambda path:False if path==tmp_path/'schema-evidence.json' else original(path))
    assert p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json')['code']=='REPAIR_PATH_REDIRECTED'


def test_source_changed_after_integrity_validation_is_not_assessed(tmp_path,monkeypatch):
    make_fixture(tmp_path)
    original=p.w.validate_release
    changed=False
    def validate(root,*args,**kwargs):
        nonlocal changed
        result=original(root,*args,**kwargs)
        if not changed and result['status']=='PASS':
            (root/'run_coordinator.py').write_text('tampered after validation')
            changed=True
        return result
    monkeypatch.setattr(p.w,'validate_release',validate)
    assert p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json')['status']=='BLOCKED'


def test_prepared_journal_before_previous_pointer_write_is_assessed(tmp_path):
    make_fixture(tmp_path,'prepared')
    (tmp_path/'current.version').write_text(PREVIOUS)
    (tmp_path/'pending.version').unlink()
    (tmp_path/'previous.version').write_text(REVIEWED)  # older valid fallback
    result=p.assess(tmp_path,REVIEWED,tmp_path/'schema-evidence.json')
    assert result['status']=='PLAN_ONLY' and result['journal_target']==PREVIOUS
    assert result['repair_authorized'] is False
