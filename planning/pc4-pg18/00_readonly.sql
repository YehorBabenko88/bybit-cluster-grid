\set ON_ERROR_STOP on
BEGIN READ ONLY;
SELECT current_setting('server_version_num') AS version_num,
       current_database(), session_user, inet_server_addr(), inet_server_port();
SELECT system_identifier FROM pg_catalog.pg_control_system();
SELECT datname, oid, pg_catalog.pg_get_userbyid(datdba) AS owner,
       datallowconn, datconnlimit, pg_catalog.pg_encoding_to_char(encoding) AS encoding,
       COALESCE(datacl,pg_catalog.acldefault('d',datdba)) AS database_acl
FROM pg_catalog.pg_database ORDER BY datname;
SELECT rolname, oid, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin,
       rolreplication, rolbypassrls
FROM pg_catalog.pg_roles
WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname;
SELECT count(*) AS other_clients
FROM pg_catalog.pg_stat_activity
WHERE backend_type='client backend' AND pid<>pg_catalog.pg_backend_pid();
COMMIT;
