"""Offline migration runner/commissioning contracts; no PostgreSQL connection."""
import asyncio
from contextlib import asynccontextmanager
import copy
import json
from pathlib import Path
import ast
import pytest
from grid import migrations as m
from installer import windows_preflight as w

INDEX48=(48,'model_registry_dataset_lookup_index',[
    'CREATE INDEX IF NOT EXISTS idx_model_registry_dataset_id ON public.model_registry(dataset_id)'])
SHA='9ab1f5b85ec471ea21ec89f1b76740c0b01537b6'


def historical(root,rows=None):
    p=root/'grid/migrations.py';p.parent.mkdir(parents=True,exist_ok=True)
    if rows is None:
        p.write_text((Path(__file__).parent/'fixtures/legacy_rollback_migrations.txt').read_text(),encoding='utf-8')
    else:p.write_text('MIGRATIONS='+repr(rows),encoding='utf-8')


def original47():return [copy.deepcopy(r) for r in m.MIGRATIONS if r[0]<=47]


@pytest.mark.parametrize('current',[47,48])
def test_historical34_validates_with_reviewed_current47_and48(tmp_path,monkeypatch,current):
    historical(tmp_path)
    catalogue=original47()+([copy.deepcopy(INDEX48)] if current==48 else [])
    monkeypatch.setattr(m,'MIGRATIONS',catalogue)
    assert w.validate_legacy_catalogue(tmp_path,SHA) is True


@pytest.mark.parametrize('damage',['unknown49','unknown48','sql34','source47','source48'])
def test_legacy_catalogue_rejects_unreviewed_extension_and_historical_change(tmp_path,monkeypatch,damage):
    current=original47()+[copy.deepcopy(INDEX48)]
    rows=copy.deepcopy(current[:34])
    if damage=='unknown49':current.append((49,'unknown_migration',['SELECT 1']))
    if damage=='unknown48':current[-1]=(48,'unknown_migration',['SELECT 1'])
    if damage=='sql34':rows[-1][2].append('DROP TABLE candles_1m')
    if damage=='source47':rows=copy.deepcopy(current[:47])
    if damage=='source48':rows=copy.deepcopy(current)
    historical(tmp_path,rows)
    monkeypatch.setattr(m,'MIGRATIONS',current)
    assert w.validate_legacy_catalogue(tmp_path,SHA) is False


def test_migration_sequence_and_exact_index_contract():
    assert [v for v,_,_ in m.MIGRATIONS]==list(range(1,49))
    assert m.MIGRATIONS[46][1]=='collection_ownership_fencing'
    assert m.MIGRATIONS[47]==INDEX48


class Connection:
    def __init__(self,rows,fail=None):
        self.rows=copy.deepcopy(rows);self.index=False;self.sql=[];self.fail=fail
    async def execute(self,sql,*args):
        self.sql.append(sql)
        if sql==INDEX48[2][0]:
            if self.fail=='sql':raise RuntimeError('synthetic SQL error')
            self.index=True
        if sql.startswith('INSERT INTO schema_migrations'):
            if args[0]==48 and self.fail=='ledger':raise RuntimeError('synthetic ledger error')
            self.rows.append({'version':args[0],'name':args[1]})
    async def fetch(self,*args):return copy.deepcopy(self.rows)
    async def fetchrow(self,*args):return copy.deepcopy(INDEX_EVIDENCE) if self.index else None
    @asynccontextmanager
    async def transaction(self):
        rows,index=copy.deepcopy(self.rows),self.index
        try:yield
        except BaseException:self.rows,self.index=rows,index;raise


class Pool:
    def __init__(self,c):self.c=c
    @asynccontextmanager
    async def acquire(self):yield self.c


def test_upgrade48_repeated_run_and_name_mismatch_before_sql():
    async def run():
        c=Connection([{'version':v,'name':n} for v,n,_ in original47()])
        await m.apply_migrations(Pool(c));await m.apply_migrations(Pool(c))
        assert c.rows[-1]=={'version':48,'name':'model_registry_dataset_lookup_index'}
        assert c.index and c.sql.count(INDEX48[2][0])==1
        c.rows[-1]['name']='wrong_index_migration'
        before=len(c.sql)
        with pytest.raises(RuntimeError,match='name mismatch'):await m.apply_migrations(Pool(c))
        assert INDEX48[2][0] not in c.sql[before:]
        assert 'pg_advisory_unlock' in c.sql[-1]
    asyncio.run(run())


@pytest.mark.parametrize('failure',['sql','ledger'])
def test_failed48_rolls_back_sql_and_ledger_then_retry_succeeds(failure):
    async def run():
        rows=[{'version':v,'name':n} for v,n,_ in original47()]
        c=Connection(rows,failure)
        with pytest.raises(RuntimeError,match='synthetic'):await m.apply_migrations(Pool(c))
        assert c.rows==rows and c.index is False
        assert 'pg_advisory_unlock' in c.sql[-1]
        c.fail=None
        await m.apply_migrations(Pool(c))
        assert c.index and c.rows[-1]['version']==48
    asyncio.run(run())


INDEX_EVIDENCE={'is_valid':True,'is_ready':True,'is_live':True,'is_unique':False,
    'not_partial':True,'no_expressions':True,'keys':1,'attributes':1,
    'table_schema':'public','table_name':'model_registry','method':'btree','columns':['dataset_id'],
    'opclass_is_builtin_uuid':True,'collation_oid':0,'key_options':0,
    'key_type_is_uuid':True,'no_opclass_options':True,'no_storage_options':True,
    'index_kind':'i','table_kind':'r','index_persistence':'p','table_persistence':'p',
    'is_primary':False,'is_exclusion':False,'nulls_not_distinct':False}


class ReadOnlyEvidence:
    def __init__(self,version,index=None):self.version=version;self.index=index
    @asynccontextmanager
    async def transaction(self,**kw):
        assert kw=={'readonly':True}
        yield
    async def fetchval(self,sql,*args):
        if 'current_database' in sql:return 'bybit_cluster_grid'
        if 'to_regclass' in sql:return args[0]
        if 'state FROM grid_runtime_state' in sql:return 'STOPPED'
        if 'EXISTS' in sql:return False
        raise AssertionError(sql)
    async def fetch(self,sql,*args):
        if 'information_schema' in sql:return [{'table_name':t,'column_name':n,'udt_name':k} for (t,n),k in w.COLUMNS.items()]
        rows=original47()+([copy.deepcopy(INDEX48)] if self.version==48 else [])
        return [{'version':v,'name':n} for v,n,_ in rows]
    async def fetchrow(self,sql,*args):return self.index
    async def execute(self,*args):raise AssertionError('preflight wrote SQL')


def test_commissioning48_and_legacy47_remain_distinct():
    async def run():
        result=await w.database_status(ReadOnlyEvidence(48,INDEX_EVIDENCE),'bybit_cluster_grid')
        assert result=={'status':'PASS','code':'DATABASE_READY','migration':48,'runtime_state':'STOPPED'}
        assert (await w.database_status(ReadOnlyEvidence(47),'bybit_cluster_grid'))['code']=='MIGRATION_CATALOGUE_MISMATCH'
        assert (await w.database_status(ReadOnlyEvidence(47),'bybit_cluster_grid',legacy_rollback=True))['code']=='LEGACY_SCHEMA47_READY_OFFLINE_ONLY'
        assert (await w.database_status(ReadOnlyEvidence(48,INDEX_EVIDENCE),'bybit_cluster_grid',legacy_rollback=True))['code']=='MIGRATION_CATALOGUE_MISMATCH'
    asyncio.run(run())


@pytest.mark.parametrize('index',[None,{**INDEX_EVIDENCE,'is_valid':False},
    {**INDEX_EVIDENCE,'columns':['model_family']},{**INDEX_EVIDENCE,'table_schema':'foreign'},
    {**INDEX_EVIDENCE,'method':'hash'},{**INDEX_EVIDENCE,'not_partial':False}])
def test_schema48_ledger_does_not_hide_wrong_or_absent_index(index):
    result=asyncio.run(w.database_status(ReadOnlyEvidence(48,index),'bybit_cluster_grid'))
    assert result['code']=='MODEL_REGISTRY_INDEX_INVALID'


@pytest.mark.parametrize('trusted',[47,48])
def test_corrupt_legacy_manifest_is_rejected_with_both_current_catalogues(tmp_path,monkeypatch,trusted):
    from test_legacy_rollback_preflight import release
    release(tmp_path,SHA)
    monkeypatch.setattr(m,'MIGRATIONS',original47()+([copy.deepcopy(INDEX48)] if trusted==48 else []))
    (tmp_path/'grid/migrations.py').write_text('MIGRATIONS=[]')
    assert w.validate_release(tmp_path,SHA,legacy_rollback=True)['code']=='RELEASE_HASH_MISMATCH'


@pytest.mark.parametrize('port',[55432,55433])
def test_disposable_database_guard_refuses_installed_ports_without_connect(monkeypatch,port):
    import _postgres_test_database as db
    monkeypatch.setenv('GRID_DISPOSABLE_POSTGRES_TESTS','1')
    monkeypatch.setenv('POSTGRES_DSN',f'postgresql://fixture@127.0.0.1:{port}/grid')
    async def forbidden(*args,**kwargs):raise AssertionError('connection attempted')
    monkeypatch.setattr(db.asyncpg,'connect',forbidden)
    async def run():
        with pytest.raises(RuntimeError,match='prohibited'):
            async with db.disposable_database():raise AssertionError('database created')
    asyncio.run(run())


def test_release_manifest_rejects_modified_migration48_source(tmp_path):
    import hashlib
    files={'run_coordinator.py':'pass','grid/control_runtime.py':'pass',
           'grid/collection_ownership.py':'pass','grid/retention.py':'pass',
           'grid/migrations.py':Path(m.__file__).read_text(encoding='utf-8')}
    for name,text in files.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    manifest={'version':'a'*40,'files':{n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in files}}
    (tmp_path/'release-manifest.json').write_text(json.dumps(manifest))
    assert w.validate_release(tmp_path,'a'*40)['status']=='PASS'
    (tmp_path/'grid/migrations.py').write_text('tampered migration48')
    assert w.validate_release(tmp_path,'a'*40)['code']=='RELEASE_HASH_MISMATCH'


@pytest.mark.parametrize('index',[None,{**INDEX_EVIDENCE,'columns':['model_family']},
    {**INDEX_EVIDENCE,'is_valid':False}])
def test48_conflicting_existing_index_never_records_version(index):
    class Conflict(Connection):
        async def execute(self,sql,*args):
            if sql==INDEX48[2][0]:self.sql.append(sql);return # IF NOT EXISTS skipped
            return await super().execute(sql,*args)
        async def fetchrow(self,*args):return index
    async def run():
        rows=[{'version':v,'name':n} for v,n,_ in original47()]
        c=Conflict(rows)
        with pytest.raises(RuntimeError,match='index'):await m.apply_migrations(Pool(c))
        assert c.rows==rows
        assert 'pg_advisory_unlock' in c.sql[-1]
    asyncio.run(run())


def test48_correct_existing_index_is_accepted_without_rebuild():
    c=Connection([{'version':v,'name':n} for v,n,_ in original47()]);c.index=True
    asyncio.run(m.apply_migrations(Pool(c)))
    assert c.rows[-1]=={'version':48,'name':'model_registry_dataset_lookup_index'}
    assert c.index is True


def test48_recorded_but_damaged_index_fails_replay_closed():
    c=Connection([{'version':v,'name':n} for v,n,_ in m.MIGRATIONS]);c.index=False
    with pytest.raises(RuntimeError,match='index'):asyncio.run(m.apply_migrations(Pool(c)))

# Query-aware catalogue double: PostgreSQL returns only SELECTed metadata. This
# reproduces omitted checks offline; real DDL cases live in test_migration48_postgres.
DEFINITION_EVIDENCE = {
    'opclass_is_builtin_uuid': True, 'collation_oid': 0, 'key_options': 0,
    'key_type_is_uuid': True, 'no_opclass_options': True, 'no_storage_options': True,
    'index_kind': 'i', 'table_kind': 'r', 'index_persistence': 'p', 'table_persistence': 'p',
    'is_primary': False, 'is_exclusion': False, 'nulls_not_distinct': False,
}


def projected_index(sql, changes):
    import re
    data = {**INDEX_EVIDENCE, **DEFINITION_EVIDENCE, **changes}
    selected = set(re.findall(r'\bAS\s+(\w+)', sql, re.IGNORECASE))
    return {k: v for k, v in data.items() if k in selected}


WRONG_DEFINITIONS = [
    ('opclass_is_builtin_uuid', False), ('collation_oid', 100),
    ('key_options', 1), ('key_options', 2), ('key_options', 3),
    ('key_type_is_uuid', False), ('no_opclass_options', False),
    ('no_storage_options', False), ('index_kind', 'I'), ('table_kind', 'm'),
    ('index_persistence', 'u'), ('table_persistence', 'u'),
    ('is_primary', True), ('is_exclusion', True), ('nulls_not_distinct', True),
]


@pytest.mark.parametrize('field,value', WRONG_DEFINITIONS)
@pytest.mark.parametrize('recorded', [False, True])
def test48_definition_mismatch_blocks_registration_and_replay(field, value, recorded):
    class Existing(Connection):
        async def execute(self, sql, *args):
            if sql == INDEX48[2][0]:
                self.sql.append(sql)  # existing index: IF NOT EXISTS does nothing
                return
            return await super().execute(sql, *args)
        async def fetchrow(self, sql, *args):
            return projected_index(sql, {field: value})
    rows = [{'version': v, 'name': n} for v, n, _ in (m.MIGRATIONS if recorded else original47())]
    c = Existing(rows)
    with pytest.raises(RuntimeError, match='index invariant'):
        asyncio.run(m.apply_migrations(Pool(c)))
    assert c.rows == rows
    assert not any(sql.startswith('INSERT INTO schema_migrations') for sql in c.sql)
    assert 'pg_advisory_unlock' in c.sql[-1]


@pytest.mark.parametrize('field,value', WRONG_DEFINITIONS)
def test_modern_commissioning_rejects_the_same_definition_mismatches(field, value):
    class Evidence(ReadOnlyEvidence):
        async def fetchrow(self, sql, *args):
            return projected_index(sql, {field: value})
    assert asyncio.run(w.database_status(Evidence(48), 'bybit_cluster_grid'))['code'] == 'MODEL_REGISTRY_INDEX_INVALID'


def test_migration_and_commissioning_share_validator():
    from grid.migration48_index import model_registry_index_ready
    assert m.model_registry_index_ready is w.model_registry_index_ready is model_registry_index_ready
