\set ON_ERROR_STOP on
\if :{?execute}
\else
  \set execute false
\endif
\if :execute
  \set _operation bootstrap
  \set _database postgres
  \ir _context.sql
  \ir _owned.sql
  BEGIN;
  SELECT format('CREATE ROLE %I NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',name)
  FROM (VALUES ('grid_integration_test_owner'),('grid_integration_test_app'),('grid_integration_test_ro')) n(name)
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=name) \gexec
  SELECT format('COMMENT ON ROLE %I IS %L',name,:'_tag')
  FROM (VALUES ('grid_integration_test_owner'),('grid_integration_test_app'),('grid_integration_test_ro')) n(name) \gexec
  COMMIT;
  -- Retain these non-secret OIDs even if subsequent database creation fails.
  SELECT rolname,oid FROM pg_roles WHERE rolname IN
    ('grid_integration_test_owner','grid_integration_test_app','grid_integration_test_ro') ORDER BY rolname;
  SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='grid_integration_test') AS _exists \gset
  \if :_exists
    \echo VERIFIED_EXISTING_DATABASE_NO_RECREATE
  \else
    -- Must remain outside a transaction. Crash before the following COMMIT leaves
    -- an unmarked database: retry/rollback then BLOCKED, never automatic adoption.
    CREATE DATABASE grid_integration_test OWNER grid_integration_test_owner
      TEMPLATE template0 ENCODING 'UTF8' CONNECTION LIMIT 0;
    BEGIN;
    COMMENT ON DATABASE grid_integration_test IS :'_tag';
    REVOKE ALL ON DATABASE grid_integration_test FROM PUBLIC;
    GRANT CONNECT ON DATABASE grid_integration_test TO grid_integration_test_app,grid_integration_test_ro;
    COMMIT;
  \endif
  SELECT oid AS expected_db_oid,datname FROM pg_database WHERE datname='grid_integration_test';
  \echo BOOTSTRAP_PREPARATION_ONLY_NO_LOGIN_NO_RUNTIME
\else
  \echo PLAN_ONLY_NO_MUTATIONS_EXECUTE_NOT_AUTHORIZED
\endif
