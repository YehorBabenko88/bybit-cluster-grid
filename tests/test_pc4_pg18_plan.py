"""Offline plan/parser checks. No PostgreSQL connection or SQL execution."""
import ast
import pathlib
import re
import json
import hashlib
import pytest
from pglast import parse_sql, parse_plpgsql
from grid.migrations import MIGRATIONS

ROOT=pathlib.Path(__file__).resolve().parents[1]
SQL=ROOT/'planning/pc4-pg18'

def test_catalogue_is_48_and_not_main_46():
    assert [m[0] for m in MIGRATIONS]==list(range(1,49))
    assert MIGRATIONS[46][1]=='collection_ownership_fencing'
    assert MIGRATIONS[47][1]=='model_registry_dataset_lookup_index'

@pytest.mark.parametrize('name',['10_bootstrap.sql','20_privileges.sql','30_rollback.sql'])
def test_mutation_files_are_explicitly_gated(name):
    s=(SQL/name).read_text()
    assert s.index('\\if :execute')<s.index('\\ir _context.sql')
    assert '\\set execute false' in s and 'PLAN_ONLY' in s
    assert '\\set ON_ERROR_STOP on' in s

def test_no_secret_or_broad_cleanup():
    s='\n'.join(p.read_text() for p in SQL.glob('*.sql'))
    assert s
    for forbidden in ('PASSWORD','DROP OWNED','REASSIGN OWNED','CASCADE','pg_terminate_backend',
                      'ALTER SYSTEM','pg_hba','CREATE EXTENSION','WITH (FORCE)'):
        assert forbidden not in s.upper() if forbidden.isupper() else forbidden not in s
    assert 'grid_integration_test' in s

def test_readonly_file_is_transaction_readonly():
    s=(SQL/'00_readonly.sql').read_text()
    assert 'BEGIN READ ONLY' in s and 'COMMIT;' in s
    assert not re.search(r'\b(CREATE|ALTER|DROP|GRANT|REVOKE)\b',s)

def test_rollback_refuses_nonpristine_or_external_resources():
    s=(SQL/'30_rollback.sql').read_text()
    combined=s+(SQL/'_context.sql').read_text()+(SQL/'_owned.sql').read_text()
    for token in ('expected_db_oid','pg_shdepend','pg_auth_members','pg_stat_activity'):
        assert token in combined
    assert s.index('BLOCKED_DATABASE_RETAINED')<s.index('DROP ROLE')
    assert 'DROP DATABASE' not in s

def test_context_is_cluster_pinned_and_superuser_only():
    s=(SQL/'_context.sql').read_text()
    for token in ('180004','pg_control_system','expected_system_identifier','session_user',
                  'pg_try_advisory_lock','127.0.0.1','5432'):
        assert token in s

def test_bootstrap_never_adopts_an_existing_name():
    s=(SQL/'_owned.sql').read_text()+(SQL/'_context.sql').read_text()
    for token in ('shobj_description','expected_owner_oid','expected_app_oid','expected_ro_oid',
                  'expected_db_oid','rolsuper','rolcanlogin','rolbypassrls','pg_auth_members'):
        assert token in s

def test_minimum_grants_do_not_make_app_owner():
    s=(SQL/'20_privileges.sql').read_text()
    assert 'SELECT,INSERT,UPDATE,DELETE ON ALL TABLES' in s
    assert "'candles_1m','footprint_1m','derivatives_metrics'" in s
    assert 'ALTER DEFAULT PRIVILEGES FOR ROLE grid_integration_test_owner' in s
    assert not re.search(r'GRANT grid_integration_test_owner\s+TO',s)
    assert 'CONNECTION LIMIT 0' in (SQL/'10_bootstrap.sql').read_text()

def test_readonly_has_no_blanket_or_future_auth_table_grants():
    s=(SQL/'20_privileges.sql').read_text()
    assert 'GRANT SELECT ON ALL TABLES' not in s
    assert 'GRANT SELECT ON TABLES TO grid_integration_test_ro' not in s

def test_real_runtime_still_requires_ddl():
    # Document the blocker instead of granting owner privileges to runtime.
    tree=ast.parse((ROOT/'grid/db.py').read_text())
    assert any(isinstance(n,ast.Constant) and isinstance(n.value,str) and 'CREATE TABLE' in n.value
               for n in ast.walk(tree))
    assert 'ensure_retention_schema(db.pool)' in (ROOT/'grid/coordinator.py').read_text()

def sql_text(name):
    s=(SQL/name).read_text()
    s=re.sub(r"\b:[']([A-Za-z_][A-Za-z0-9_]*)[']", "'synthetic'",s)
    s=re.sub(r":[']([A-Za-z_][A-Za-z0-9_]*)[']", "'synthetic'",s)
    s=re.sub(r'(?m)^\s*\\[^\n]*','',s)
    return re.sub(r'\\g(?:set|exec)[^\n]*',';',s)

@pytest.mark.parametrize('name',['00_readonly.sql','_context.sql','_owned.sql',
    '10_bootstrap.sql','20_privileges.sql','30_rollback.sql'])
def test_sql_grammar_offline(name):
    assert parse_sql(sql_text(name))

@pytest.mark.parametrize('name',['_context.sql','_owned.sql','20_privileges.sql','30_rollback.sql'])
def test_plpgsql_grammar_offline(name):
    blocks=re.findall(r'DO\s+(\$[A-Za-z_]+\$)(.*?)\1\s*;',sql_text(name),re.S)
    assert blocks
    for tag,body in blocks:
        assert parse_plpgsql('DO '+tag+body+tag+';')

def test_readonly_login_and_connection_activation_are_not_implemented():
    s='\n'.join(p.read_text() for p in SQL.glob('*.sql'))
    assert not re.search(r'ALTER ROLE[^;]+\bLOGIN\b',s)
    assert 'CONNECTION LIMIT 20' not in s and 'CONNECTION LIMIT -1' not in s

def test_partial_create_failure_requires_manual_review():
    s=(SQL/'10_bootstrap.sql').read_text()
    assert s.index('CREATE DATABASE')<s.index('COMMENT ON DATABASE')
    guard=(SQL/'_owned.sql').read_text()
    assert "shobj_description(d.oid,'pg_database') IS DISTINCT FROM tag" in guard
    assert "current_setting('grid.pc4.db_oid')='0'" in guard

def test_privileges_refuse_drift_before_any_grants():
    s=(SQL/'20_privileges.sql').read_text()
    assert s.index('BLOCKED_UNEXPECTED_OBJECT_ACL')<s.index('ALTER SCHEMA')
    assert 'pg_default_acl' in s and 'attacl' in s

def test_rollback_has_no_incomplete_catalog_pristine_test():
    s=(SQL/'30_rollback.sql').read_text()
    assert "NOT LIKE 'pg_%'" not in s
    assert 'FULL_CATALOG_PROOF_REQUIRED' in s
    assert 'pg_class' not in s and 'DROP DATABASE' not in s

def test_catalogue_receipt_matches_actual_names_and_sql():
    receipt=json.loads((SQL/'migrations.json').read_text())
    expected=[dict(version=v,name=n,sql_sha256=hashlib.sha256(
        json.dumps(sql,ensure_ascii=True,separators=(',',':')).encode()).hexdigest())
        for v,n,sql in MIGRATIONS]
    assert receipt['catalogue']==expected

def test_plan_branch_cannot_start_infrastructure():
    branch='planning/pc4-pg18-bootstrap-20261022'
    pure={'pc4-sid-acl-offline.yml','pgdata-intent-offline.yml','lab-airgap-a.yml',
          'lab-witness-l1.yml','windows-lab-planning.yml','offline-rc-review.yml','protected-staging-offline.yml'}
    for p in (ROOT/'.github/workflows').glob('*.yml'):
        s=p.read_text()
        for job in re.split(r'(?m)^  [A-Za-z0-9_-]+:\n',s.split('jobs:\n',1)[1])[1:]:
            first=job.splitlines()[0]
            if p.name not in pure:
                assert f"github.head_ref != '{branch}'" in first
                assert f"github.ref_name != '{branch}'" in first
            else:
                assert 'services:' not in s and 'self-hosted' not in s

def test_existing_runtime_and_migration_sources_are_not_patched():
    import subprocess
    base='217904071394ab8a84e5a180822081ff8e25e1e9'
    assert not subprocess.check_output(['git','diff',base,'--','grid','installer','lab'],cwd=ROOT)

def test_ownership_and_public_privileges_are_not_implicit_bypasses():
    owned=(SQL/'_owned.sql').read_text();acl=(SQL/'20_privileges.sql').read_text()
    assert "x.deptype='o'" in owned and 'BLOCKED_APP_OR_RO_OBJECT_OWNER' in owned
    assert 'a.grantee=0' in acl
    assert "aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner)))" in acl
    assert "has_database_privilege('grid_integration_test_app',d.oid,'CONNECT')" in owned

def test_missing_approval_stops_with_sql_error_not_unsupported_quit_status():
    combined=(SQL/'_context.sql').read_text()+(SQL/'30_rollback.sql').read_text()
    assert '\\quit 3' not in combined
    assert "RAISE EXCEPTION 'BLOCKED_MISSING_BOOTSTRAP_ID'" in combined
    assert "RAISE EXCEPTION 'BLOCKED_SEPARATE_ROLE_CLEANUP_APPROVAL_REQUIRED'" in combined
