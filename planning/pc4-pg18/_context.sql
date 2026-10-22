-- Internal include, never invoke independently. Session settings only.
\if :{?bootstrap_id}
\else
  \echo BLOCKED_MISSING_BOOTSTRAP_ID
  \quit 3
\endif
\if :{?expected_system_identifier}
\else
  \echo BLOCKED_MISSING_CLUSTER_PIN
  \quit 3
\endif
\if :{?expected_owner_oid}
\else
  \set expected_owner_oid 0
\endif
\if :{?expected_app_oid}
\else
  \set expected_app_oid 0
\endif
\if :{?expected_ro_oid}
\else
  \set expected_ro_oid 0
\endif
\if :{?expected_db_oid}
\else
  \set expected_db_oid 0
\endif
SELECT pg_catalog.set_config('grid.pc4.id', :'bootstrap_id', false),
       pg_catalog.set_config('grid.pc4.cluster', :'expected_system_identifier', false),
       pg_catalog.set_config('grid.pc4.owner_oid', :'expected_owner_oid', false),
       pg_catalog.set_config('grid.pc4.app_oid', :'expected_app_oid', false),
       pg_catalog.set_config('grid.pc4.ro_oid', :'expected_ro_oid', false),
       pg_catalog.set_config('grid.pc4.db_oid', :'expected_db_oid', false),
       pg_catalog.set_config('grid.pc4.operation', :'_operation', false),
       pg_catalog.set_config('grid.pc4.database', :'_database', false);
SET search_path=pg_catalog;
SET lock_timeout='5s';
SET statement_timeout='30s';
DO $context$
DECLARE key text;
BEGIN
  IF current_setting('server_version_num') <> '180004'
     OR current_database() <> current_setting('grid.pc4.database')
     OR session_user <> 'postgres' OR current_user <> session_user
     OR NOT (SELECT rolsuper FROM pg_roles WHERE rolname=session_user)
     OR inet_server_addr() IS DISTINCT FROM '127.0.0.1'::inet
     OR inet_server_port() IS DISTINCT FROM 5432 THEN
    RAISE EXCEPTION 'BLOCKED_ENDPOINT_VERSION_OR_ADMIN';
  END IF;
  IF current_setting('grid.pc4.id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR current_setting('grid.pc4.cluster') !~ '^[1-9][0-9]{0,19}$'
     OR (SELECT system_identifier::text FROM pg_control_system()) <> current_setting('grid.pc4.cluster') THEN
    RAISE EXCEPTION 'BLOCKED_CLUSTER_OR_RUN_ID';
  END IF;
  FOREACH key IN ARRAY ARRAY['owner_oid','app_oid','ro_oid','db_oid'] LOOP
    IF current_setting('grid.pc4.'||key) !~ '^(0|[1-9][0-9]{0,9})$'
       OR current_setting('grid.pc4.'||key)::numeric > 4294967295 THEN
      RAISE EXCEPTION 'BLOCKED_OID_PIN';
    END IF;
  END LOOP;
  IF NOT pg_try_advisory_lock(1800043912::bigint) THEN
    RAISE EXCEPTION 'BLOCKED_CONCURRENT_PLAN_SESSION';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_stat_activity WHERE backend_type='client backend'
             AND pid<>pg_backend_pid()) THEN
    RAISE EXCEPTION 'BLOCKED_OTHER_CLIENTS';
  END IF;
END;
$context$;
SELECT 'grid-pc4-v1:'||current_setting('grid.pc4.id')||':'||current_setting('grid.pc4.cluster') AS _tag \gset
