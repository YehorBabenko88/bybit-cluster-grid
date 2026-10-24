-- OPERATOR-ONLY G0. Never automatically invoked. No passwords/role names/rows.
-- Requires separately verified PostgreSQL binary, destination and read-only access.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='1s';
SELECT current_setting('server_version_num') AS server_version_num,
       current_setting('transaction_read_only') AS transaction_read_only;
SELECT oid AS database_oid,datdba AS owner_oid,datistemplate,datallowconn
  FROM pg_catalog.pg_database ORDER BY oid;
SELECT oid AS role_oid,rolsuper,rolinherit,rolcreaterole,rolcreatedb,
       rolcanlogin,rolreplication,rolbypassrls FROM pg_catalog.pg_roles ORDER BY oid;
SELECT member,roleid,admin_option FROM pg_catalog.pg_auth_members ORDER BY member,roleid;
SELECT count(*) AS other_client_connections FROM pg_catalog.pg_stat_activity
 WHERE backend_type='client backend' AND pid<>pg_backend_pid();
ROLLBACK;
