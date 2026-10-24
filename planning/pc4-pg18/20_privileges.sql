\set ON_ERROR_STOP on
\if :{?execute}
\else
  \set execute false
\endif
\if :execute
  \set _operation privileges
  \set _database grid_integration_test
  \ir _context.sql
  \ir _owned.sql
  BEGIN;
  DO $acl_drift$
  DECLARE app_oid oid; ro_oid oid; owner_oid oid; public_oid oid;
  BEGIN
    SELECT oid INTO app_oid FROM pg_roles WHERE rolname='grid_integration_test_app';
    SELECT oid INTO ro_oid FROM pg_roles WHERE rolname='grid_integration_test_ro';
    SELECT oid INTO owner_oid FROM pg_roles WHERE rolname='grid_integration_test_owner';
    SELECT oid INTO public_oid FROM pg_namespace WHERE nspname='public';
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
                       LATERAL aclexplode(c.relacl) a WHERE
       (a.grantee=0 AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast'))
       OR (a.grantee=ro_oid AND (n.nspname<>'public' OR c.relkind<>'r'
          OR c.relname NOT IN ('candles_1m','footprint_1m','derivatives_metrics')
          OR a.privilege_type<>'SELECT' OR a.is_grantable))
       OR (a.grantee=app_oid AND (n.nspname<>'public' OR a.is_grantable
          OR (c.relname IN ('schema_migrations','grid_schema_contract') AND a.privilege_type<>'SELECT') OR NOT
          ((c.relkind='r' AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE'))
           OR (c.relkind='S' AND a.privilege_type IN ('USAGE','SELECT'))))))
       OR EXISTS (SELECT 1 FROM pg_attribute t JOIN pg_class c ON c.oid=t.attrelid
                   JOIN pg_namespace n ON n.oid=c.relnamespace,LATERAL aclexplode(t.attacl) a
                   WHERE a.grantee IN (app_oid,ro_oid) OR (a.grantee=0 AND
                     n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')))
       OR EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace,
                   LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee IN (app_oid,ro_oid)
                     OR (a.grantee=0 AND n.nspname NOT IN ('pg_catalog','information_schema')))
       OR EXISTS (SELECT 1 FROM pg_namespace n,LATERAL aclexplode(n.nspacl) a
                   WHERE a.grantee IN (app_oid,ro_oid) AND
                     (n.oid<>public_oid OR a.privilege_type<>'USAGE' OR a.is_grantable)
                     OR (a.grantee=0 AND n.oid=public_oid AND
                       (a.privilege_type<>'USAGE' OR a.is_grantable)))
       OR EXISTS (SELECT 1 FROM pg_default_acl d,LATERAL aclexplode(d.defaclacl) a WHERE
          a.grantee=0 OR a.grantee=ro_oid OR (a.grantee=app_oid AND
            (d.defaclrole<>owner_oid OR d.defaclnamespace<>public_oid OR a.is_grantable OR NOT
             ((d.defaclobjtype='r' AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE'))
              OR (d.defaclobjtype='S' AND a.privilege_type IN ('USAGE','SELECT')))))) THEN
      RAISE EXCEPTION 'BLOCKED_UNEXPECTED_OBJECT_ACL';
    END IF;
  END;
  $acl_drift$;
  ALTER SCHEMA public OWNER TO grid_integration_test_owner;
  REVOKE ALL ON SCHEMA public FROM PUBLIC;
  GRANT USAGE ON SCHEMA public TO grid_integration_test_app,grid_integration_test_ro;
  SET LOCAL ROLE grid_integration_test_owner;
  GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO grid_integration_test_app;
  -- Immutable runtime contract metadata is owner-only. Broad market/control
  -- DML grants must never permit the app to rewrite migration or schema seals.
  REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON
    public.schema_migrations,public.grid_schema_contract FROM grid_integration_test_app;
  GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO grid_integration_test_app;
  -- RO is a market-data allowlist, never enrollment/control credentials or
  -- automatic access to future tables. Rerun after a separately reviewed migration.
  DO $market_ro$
  DECLARE relation record;
  BEGIN
    FOR relation IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind='r'
      AND c.relname IN ('candles_1m','footprint_1m','derivatives_metrics') LOOP
      EXECUTE format('GRANT SELECT ON TABLE public.%I TO grid_integration_test_ro',relation.relname);
    END LOOP;
  END;
  $market_ro$;
  ALTER DEFAULT PRIVILEGES FOR ROLE grid_integration_test_owner IN SCHEMA public
    GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO grid_integration_test_app;
  ALTER DEFAULT PRIVILEGES FOR ROLE grid_integration_test_owner IN SCHEMA public
    GRANT USAGE,SELECT ON SEQUENCES TO grid_integration_test_app;
  ALTER DEFAULT PRIVILEGES FOR ROLE grid_integration_test_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
  RESET ROLE;
  ALTER ROLE grid_integration_test_owner IN DATABASE grid_integration_test SET search_path=public,pg_catalog;
  ALTER ROLE grid_integration_test_app IN DATABASE grid_integration_test SET search_path=public,pg_catalog;
  ALTER ROLE grid_integration_test_ro IN DATABASE grid_integration_test SET search_path=public,pg_catalog;
  ALTER ROLE grid_integration_test_ro IN DATABASE grid_integration_test SET default_transaction_read_only=on;
  COMMIT;
  \echo PRIVILEGES_PREPARED_APP_STARTUP_STILL_BLOCKED
\else
  \echo PLAN_ONLY_NO_MUTATIONS_EXECUTE_NOT_AUTHORIZED
\endif
