-- Verify provenance and externally retained OID pins BEFORE mutations.
DO $owned$
DECLARE r record; d record; expected text; tag text;
BEGIN
  tag := 'grid-pc4-v1:'||current_setting('grid.pc4.id')||':'||current_setting('grid.pc4.cluster');
  FOR r IN SELECT n.name, n.pin, p.* FROM
    (VALUES ('grid_integration_test_owner','owner_oid'),
            ('grid_integration_test_app','app_oid'),
            ('grid_integration_test_ro','ro_oid')) AS n(name,pin)
    LEFT JOIN pg_roles p ON p.rolname=n.name LOOP
    expected:=current_setting('grid.pc4.'||r.pin);
    IF r.oid IS NULL THEN
      IF expected<>'0' AND current_setting('grid.pc4.operation')<>'rollback' THEN
        RAISE EXCEPTION 'BLOCKED_EXPECTED_ROLE_MISSING';
      END IF;
    ELSIF expected='0' OR r.oid::text<>expected
       OR shobj_description(r.oid,'pg_authid') IS DISTINCT FROM tag
       OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolcanlogin
       OR r.rolreplication OR r.rolbypassrls OR r.rolinherit
       OR r.rolconfig IS NOT NULL OR r.rolvaliduntil IS NOT NULL
       OR EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid=r.oid OR member=r.oid) THEN
      RAISE EXCEPTION 'BLOCKED_ROLE_COLLISION_OR_DRIFT';
    END IF;
  END LOOP;
  SELECT * INTO d FROM pg_database WHERE datname='grid_integration_test';
  IF FOUND THEN
    IF current_setting('grid.pc4.db_oid')='0' OR d.oid::text<>current_setting('grid.pc4.db_oid')
       OR shobj_description(d.oid,'pg_database') IS DISTINCT FROM tag
       OR d.datdba IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname='grid_integration_test_owner')
       OR d.datconnlimit<>0 OR NOT d.datallowconn OR d.datistemplate OR d.datacl IS NULL
       OR pg_encoding_to_char(d.encoding)<>'UTF8'
       OR NOT has_database_privilege('grid_integration_test_app',d.oid,'CONNECT')
       OR NOT has_database_privilege('grid_integration_test_ro',d.oid,'CONNECT')
       OR has_database_privilege('grid_integration_test_app',d.oid,'CREATE')
       OR has_database_privilege('grid_integration_test_app',d.oid,'TEMP')
       OR has_database_privilege('grid_integration_test_ro',d.oid,'CREATE')
       OR has_database_privilege('grid_integration_test_ro',d.oid,'TEMP')
       OR (SELECT count(*) FROM pg_roles WHERE rolname IN
           ('grid_integration_test_owner','grid_integration_test_app','grid_integration_test_ro'))<>3
       OR EXISTS (SELECT 1 FROM aclexplode(d.datacl) a WHERE
           a.grantee NOT IN (SELECT oid FROM pg_roles WHERE rolname IN
             ('grid_integration_test_owner','grid_integration_test_app','grid_integration_test_ro'))
           OR (a.grantee<>d.datdba AND (a.privilege_type<>'CONNECT' OR a.is_grantable))) THEN
      RAISE EXCEPTION 'BLOCKED_DATABASE_COLLISION_OR_DRIFT';
    END IF;
  ELSIF current_setting('grid.pc4.db_oid')<>'0' AND current_setting('grid.pc4.operation')<>'rollback' THEN
    RAISE EXCEPTION 'BLOCKED_EXPECTED_DATABASE_MISSING';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_shdepend x WHERE x.refclassid='pg_authid'::regclass
      AND x.refobjid IN (SELECT oid FROM pg_roles WHERE rolname IN
        ('grid_integration_test_owner','grid_integration_test_app','grid_integration_test_ro'))
      AND NOT (d.oid IS NOT NULL AND (x.dbid=d.oid OR
        (x.dbid=0 AND x.classid='pg_database'::regclass AND x.objid=d.oid)))) THEN
    RAISE EXCEPTION 'BLOCKED_EXTERNAL_ROLE_DEPENDENCIES';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_shdepend x WHERE x.refclassid='pg_authid'::regclass
      AND x.deptype='o' AND x.refobjid IN (SELECT oid FROM pg_roles
        WHERE rolname IN ('grid_integration_test_app','grid_integration_test_ro'))) THEN
    RAISE EXCEPTION 'BLOCKED_APP_OR_RO_OBJECT_OWNER';
  END IF;
END;
$owned$;
