"""Synthetic source/DB evidence only; target Python is never executed."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from installer import windows_preflight as w
from grid.migrations import MIGRATIONS

VERSIONS = ['9ab1f5b85ec471ea21ec89f1b76740c0b01537b6', '2017ed4fd16b0b222173a6d42b5bf24b2beb73ac']


def release(root, sha, role='CONTROL'):
    files={'run_coordinator.py':'raise RuntimeError("must not execute target")', 'run_worker.py':'pass',
           'grid/coordinator.py':'pass', 'grid/worker.py':'pass', 'grid/db.py':'pass', 'grid/retention.py':'pass',
           'grid/migrations.py':(Path(__file__).parent/'fixtures/legacy_rollback_migrations.txt').read_text()+'\nraise RuntimeError("must not import target")'}
    for name, data in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,encoding='utf-8')
    manifest={'version':sha,'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}}
    (root/'release-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return manifest


@pytest.mark.parametrize('sha',VERSIONS)
@pytest.mark.parametrize('role',['CONTROL','WORKER'])
def test_reviewed_legacy_missing_new_modules_is_not_corruption(tmp_path,sha,role):
    release(tmp_path,sha)
    assert w.validate_release(tmp_path,sha,role)['code']=='RELEASE_PROTOCOL_FILES_MISSING'
    before=(tmp_path/'release-manifest.json').read_bytes()
    result=w.validate_release(tmp_path,sha,role,legacy_rollback=True)
    assert result['status']=='PASS'
    assert result['code']=='LEGACY_RELEASE_VERIFIED_OFFLINE_ONLY'
    assert (tmp_path/'release-manifest.json').read_bytes()==before
    assert not (tmp_path/'grid/control_runtime.py').exists()


def test_legacy_is_explicit_allowlisted_and_never_a_missing_file_fallback(tmp_path):
    release(tmp_path,'a'*40)
    assert w.validate_release(tmp_path,'a'*40,legacy_rollback=True)['code']=='LEGACY_RELEASE_NOT_REVIEWED'


@pytest.mark.parametrize('damage',['hash','missing','unverified','prefix','duplicate'])
def test_legacy_integrity_and_migration_prefix_fail_closed(tmp_path,damage):
    sha=VERSIONS[0];m=release(tmp_path,sha)
    if damage=='hash':(tmp_path/'grid/db.py').write_text('tampered')
    if damage=='missing':(tmp_path/'grid/db.py').unlink()
    if damage=='unverified':(tmp_path/'extra.py').write_text('pass')
    if damage=='prefix':
        (tmp_path/'grid/migrations.py').write_text('MIGRATIONS=[]')
        m['files']['grid/migrations.py']=hashlib.sha256((tmp_path/'grid/migrations.py').read_bytes()).hexdigest()
        (tmp_path/'release-manifest.json').write_text(json.dumps(m))
    if damage=='duplicate':
        text=json.dumps(m);(tmp_path/'release-manifest.json').write_text(text[:-1]+',"version":"'+sha+'"}')
    assert w.validate_release(tmp_path,sha,legacy_rollback=True)['status']=='BLOCKED'


class DatabaseEvidence:
    def __init__(self,kind='valid'):
        self.kind=kind;self.execute=AsyncMock()
    def transaction(self,**kw):
        assert kw=={'readonly':True}
        @asynccontextmanager
        async def tx():yield
        return tx()
    async def fetchval(self,sql,*args):
        if 'current_database' in sql:return 'bybit_cluster_grid'
        if 'to_regclass' in sql:return args[0]
        if 'state FROM grid_runtime_state' in sql:return 'ACTIVE' if self.kind=='active' else 'STOPPED'
        if 'EXISTS' in sql:return self.kind=='lease'
        raise AssertionError(sql)
    async def fetch(self,sql,*args):
        if 'information_schema' in sql:
            return [{'table_name':t,'column_name':n,'udt_name':k} for (t,n),k in w.COLUMNS.items() if not (self.kind=='columns' and n=='generation')]
        rows=[{'version':v,'name':n} for v,n,_ in MIGRATIONS if v<=47]
        if self.kind=='old':return rows[:34]
        if self.kind=='future':rows.append({'version':48,'name':'unknown'})
        if self.kind=='renamed':rows[0]['name']='unexpected'
        return rows


@pytest.mark.parametrize('kind,expected',[('valid','LEGACY_SCHEMA47_READY_OFFLINE_ONLY'),
    ('old','MIGRATION_CATALOGUE_MISMATCH'),('future','MIGRATION_CATALOGUE_MISMATCH'),
    ('renamed','MIGRATION_CATALOGUE_MISMATCH'),('active','RUNTIME_NOT_QUIESCENT'),
    ('columns','GRID_COLUMNS_INCOMPLETE'),('lease','LEGACY_RUNTIME_LEASE_ACTIVE')])
def test_schema47_legacy_compatibility_is_readonly_and_fail_closed(kind,expected):
    c=DatabaseEvidence(kind)
    assert asyncio.run(w.database_status(c,'bybit_cluster_grid',legacy_rollback=True))['code']==expected
    c.execute.assert_not_called()


def test_legacy_cli_requires_database_evidence_even_for_worker(monkeypatch,tmp_path,capsys):
    sha=VERSIONS[0];release(tmp_path,sha)
    monkeypatch.setattr(w,'check_dependencies',lambda:{'status':'PASS'})
    monkeypatch.setenv('NODE_CREDENTIAL','test-only');monkeypatch.setenv('RETENTION_ENABLED','false')
    assert w.main(['--release-dir',str(tmp_path),'--expected-sha',sha,'--role','WORKER','--legacy-rollback','--min-free-gb','0.001'])==2
    result=json.loads(capsys.readouterr().out)
    assert result['checks']['database']['code']=='LEGACY_DATABASE_CHECK_REQUIRED'
    assert result['activation_authorized'] is False
