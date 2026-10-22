\set ON_ERROR_STOP on
\if :{?execute}
\else
  \set execute false
\endif
\if :execute
  \if :{?approve_role_cleanup}
  \else
    \set approve_role_cleanup false
  \endif
  \if :approve_role_cleanup
  \else
    \echo BLOCKED_SEPARATE_ROLE_CLEANUP_APPROVAL_REQUIRED
    \quit 3
  \endif
  \set _operation rollback
  \set _database postgres
  \ir _context.sql
  \ir _owned.sql
  DO $retain$
  BEGIN
    IF EXISTS (SELECT 1 FROM pg_database WHERE datname='grid_integration_test') THEN
      RAISE EXCEPTION 'BLOCKED_DATABASE_RETAINED_FULL_CATALOG_PROOF_REQUIRED';
    END IF;
    -- No database deletion: pristine tests limited to selected catalogs are not
    -- a proof of absence of unknown objects. Never infer deletion authority.
    IF EXISTS (SELECT 1 FROM pg_shdepend d WHERE d.refclassid='pg_authid'::regclass
       AND d.refobjid IN (SELECT oid FROM pg_roles WHERE rolname IN
         ('grid_integration_test_owner','grid_integration_test_app','grid_integration_test_ro'))) THEN
      RAISE EXCEPTION 'BLOCKED_ROLE_DEPENDENCIES';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_stat_activity WHERE backend_type='client backend'
               AND pid<>pg_backend_pid()) THEN
      RAISE EXCEPTION 'BLOCKED_OTHER_CLIENTS';
    END IF;
  END;
  $retain$;
  -- pg_auth_members, markers and expected_db_oid / role OIDs were checked by
  -- the shared include. Dependency checks remain native: no automatic cleanup.
  BEGIN;
  SELECT format('DROP ROLE %I',rolname) FROM pg_roles WHERE rolname IN
    ('grid_integration_test_app','grid_integration_test_ro','grid_integration_test_owner') \gexec
  COMMIT;
  \echo CREATED_ROLES_REMOVED_OR_ALREADY_ABSENT_DATABASES_UNTOUCHED
\else
  \echo PLAN_ONLY_NO_MUTATIONS_EXECUTE_NOT_AUTHORIZED
\endif
