"""Offline regressions: no PostgreSQL connections."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
ROOT=Path(__file__).resolve().parents[1]

def test_startup_never_prepares_schema():
    tree=ast.parse((ROOT/'grid/service.py').read_text())
    startup=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='prepare_database')
    calls={getattr(n.func,'attr',getattr(n.func,'id','')) for n in ast.walk(startup) if isinstance(n,ast.Call)}
    assert not calls & {'ensure_schema','apply_migrations','prepare_schema'}
    assert 'verify_runtime_schema' in calls

def test_leader_startup_has_no_schema_ensurers():
    tree=ast.parse((ROOT/'grid/coordinator.py').read_text())
    startup=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='start_leader_services')
    calls={getattr(n.func,'id','') for n in ast.walk(startup) if isinstance(n,ast.Call)}
    assert not any(n.startswith('ensure_') for n in calls)

@pytest.mark.parametrize('module,function',[('fleet_control','latest_operation'),('fleet_control','fleet_stop'),('runtime_gate','set_runtime_state'),('rollout','begin_stable_rollout'),('bootstrap_runtime','bootstrap_runtime')])
def test_lazy_runtime_paths_do_not_prepare(module,function):
    tree=ast.parse((ROOT/f'grid/{module}.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name==function)
    for n in ast.walk(fn):
        if isinstance(n,ast.Call):
            assert getattr(n.func,'id','') not in {'ensure_fleet_schema','ensure_runtime_gate','apply_migrations'}
        if isinstance(n,ast.Constant) and isinstance(n.value,str):
            assert 'CREATE TABLE' not in n.value

def test_runtime_verification_failure_is_fatal_and_closes_pool(monkeypatch):
    from grid import service
    pool=SimpleNamespace(close=AsyncMock())
    db=SimpleNamespace(pool=pool,connect=AsyncMock(),ensure_schema=AsyncMock(side_effect=AssertionError('DDL')))
    monkeypatch.setattr(service,'Database',lambda:db)
    monkeypatch.setattr(service,'verify_runtime_schema',AsyncMock(side_effect=RuntimeError('SCHEMA_BLOCKED')),raising=False)
    with pytest.raises(RuntimeError,match='SCHEMA_BLOCKED'):
        asyncio.run(service.prepare_database())
    assert pool.close.await_count==1
    assert not db.ensure_schema.called


def test_pool_setup_pins_search_path_on_every_acquisition(monkeypatch):
    from grid import db
    c=SimpleNamespace(execute=AsyncMock())
    asyncio.run(db.configure_connection(c))
    c.execute.assert_awaited_once_with('SET search_path=pg_catalog,public')
    create=AsyncMock(return_value=object())
    monkeypatch.setattr(db.asyncpg,'create_pool',create)
    asyncio.run(db.Database().connect())
    assert create.call_args.kwargs['setup'] is db.configure_connection


def test_legacy_import_is_dml_only():
    tree=ast.parse((ROOT/'grid/legacy_bootstrap_import.py').read_text())
    for n in ast.walk(tree):
        if isinstance(n,ast.Constant) and isinstance(n.value,str):
            assert not any(x in n.value.upper() for x in ('CREATE TEMP TABLE','TRUNCATE LEGACY_'))


def test_all_grid_ddl_execute_sites_are_explicit_preparation_only():
    import re
    allowed={'db.py':{'ensure_schema'},'control_plane.py':{'ensure_control_schema'},
      'enrollment.py':{'ensure_enrollment_schema'},'fleet_control.py':{'ensure_fleet_schema'},
      'instrument_lifecycle.py':{'ensure_instrument_schema'},'retention.py':{'ensure_retention_schema'},
      'runtime_gate.py':{'ensure_runtime_gate'},'strategy_jobs.py':{'ensure_strategy_schema'},
      'strategy_plugins.py':{'ensure_plugin_schema'},'update_protocol.py':{'ensure_update_schema'},
      'migrations.py':{'apply_migrations'},'schema_preparation.py':{'prepare_schema'}}
    for path in (ROOT/'grid').glob('*.py'):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        for fn in ast.walk(tree):
            if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            for node in ast.walk(fn):
                if not isinstance(node,ast.Call) or getattr(node.func,'attr','')!='execute' or not node.args:continue
                arg=node.args[0]
                if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and re.match(r'\s*(CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE)\b',arg.value,re.I):
                    assert fn.name in allowed.get(path.name,set()),(path.name,fn.name)


def test_new_static_sql_parses_as_postgresql18():
    from pglast import parse_sql
    for name in ('schema_contract.py','schema_preparation.py','legacy_bootstrap_import.py'):
        tree=ast.parse((ROOT/'grid'/name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and getattr(node.func,'attr','') in {'execute','fetch','fetchrow','fetchval'} and node.args:
                arg=node.args[0]
                # src/rdb are read-only SQLite handles, not PostgreSQL.
                if getattr(node.func.value,'id','') in {'src','rdb'}:continue
                if isinstance(arg,ast.Constant) and isinstance(arg.value,str):parse_sql(arg.value)


def test_strategy_subprocess_validates_before_loading_plugin(monkeypatch):
    from grid import strategy_runtime as runtime
    from grid.schema_contract import SchemaBlocked
    pool=SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(runtime.asyncpg,'create_pool',AsyncMock(return_value=pool))
    monkeypatch.setattr(runtime,'verify_runtime_schema',AsyncMock(side_effect=SchemaBlocked('BLOCKED_SCHEMA')),raising=False)
    for k,v in {'GRID_STRATEGY_PLUGIN':'synthetic-never-load.py','GRID_STRATEGY_JOB_ID':'synthetic',
                'POSTGRES_DSN':'synthetic-no-connection','GRID_STRATEGY_ATTEMPT':'1','GRID_STRATEGY_NODE':'synthetic'}.items():
        monkeypatch.setenv(k,v)
    with pytest.raises(SchemaBlocked,match='BLOCKED_SCHEMA'):
        asyncio.run(runtime.main())
    pool.close.assert_awaited_once()


def test_all_runtime_pool_constructors_pin_search_path():
    found=[]
    for path in (ROOT/'grid').glob('*.py'):
        for n in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(n,ast.Call) and getattr(n.func,'attr','')=='create_pool':
                found.append(path.name)
                assert any(k.arg=='setup' and getattr(k.value,'id','')=='configure_connection' for k in n.keywords)
    assert sorted(found)==['db.py','storage.py','strategy_runtime.py']


def test_windows_synthetic_suites_use_fresh_powershell_process_exit_status():
    workflow=(ROOT/'.github/workflows/ddl-free-runtime.yml').read_text(encoding='utf-8')
    assert 'powershell.exe -NoProfile -NonInteractive -File .\\installer\\tests\\test-release-runtime-guard.ps1' in workflow
    assert 'powershell.exe -NoProfile -NonInteractive -File .\\installer\\tests\\test-legacy-rollback.ps1' in workflow
    assert "if ($LASTEXITCODE -ne 0) { throw 'LegacyRollback regression failure' }" in workflow
