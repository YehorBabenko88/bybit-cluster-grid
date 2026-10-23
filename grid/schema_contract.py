"""Read-only startup contract. This module never prepares or repairs a schema.

The seal is a trusted-owner assertion, not proof against that owner/admin.
Runtime must have neither write access to the seal/registry nor DDL authority.
"""
import hashlib
import json
from pathlib import Path

from .migrations import MIGRATIONS
from .migration48_index import model_registry_index_ready

CONTRACT_VERSION = 1
SCHEMA_SOURCES = (
    'db.py', 'migrations.py', 'collection_ownership.py', 'migration48_index.py',
    'instrument_lifecycle.py', 'strategy_jobs.py', 'strategy_plugins.py',
    'control_plane.py', 'update_protocol.py', 'enrollment.py', 'runtime_gate.py',
    'retention.py', 'fleet_control.py', 'schema_preparation.py', 'schema_contract.py',
)


class SchemaBlocked(RuntimeError):
    pass


def source_digest():
    root = Path(__file__).parent
    # Git checkout CRLF/LF must not change the contract across Windows/Linux.
    rows = [(name, (root / name).read_text(encoding='utf-8')) for name in SCHEMA_SOURCES]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


# Structural definitions, independent of object OIDs, data contents and grants.
# Include implicit PK indexes, constraints, defaults, RLS, triggers and routines.
# The preparer only seals an empty schema built from this checkout, never adopts
# unknown existing objects. Subsequent preparation verifies before doing work.
CATALOG_SQL = """
SELECT kind,name,definition FROM (
 SELECT 'relation' kind,c.relname name,
   jsonb_build_array(c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity,
                    c.reloptions,pg_get_userbyid(c.relowner))::text definition
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL
 SELECT 'column',c.relname||'.'||a.attname,
   jsonb_build_array(a.attnum,format_type(a.atttypid,a.atttypmod),a.attnotnull,
     a.attidentity,a.attgenerated,co.collname,pg_get_expr(d.adbin,d.adrelid))::text
 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace
 LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
 LEFT JOIN pg_collation co ON co.oid=a.attcollation
 WHERE n.nspname='public' AND a.attnum>0 AND NOT a.attisdropped
 UNION ALL
 SELECT 'constraint',c.relname||'.'||p.conname,
   jsonb_build_array(pg_get_constraintdef(p.oid,true),p.convalidated,to_jsonb(p)->'conenforced')::text
 FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL
 SELECT 'index',c.relname,
   jsonb_build_array(pg_get_indexdef(i.indexrelid),i.indisvalid,i.indisready,i.indislive)::text
 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL
 SELECT 'sequence',c.relname,
   jsonb_build_array(format_type(s.seqtypid,NULL),s.seqstart,s.seqincrement,s.seqmax,
                    s.seqmin,s.seqcache,s.seqcycle)::text
 FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL
 SELECT 'routine',p.proname||'('||pg_get_function_identity_arguments(p.oid)||')',
   pg_get_functiondef(p.oid)
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.prokind IN ('f','p')
 UNION ALL
 SELECT 'trigger',c.relname||'.'||t.tgname,
   jsonb_build_array(pg_get_triggerdef(t.oid),t.tgenabled)::text
 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL
 SELECT 'policy',c.relname||'.'||p.polname,to_jsonb(p)::text
 FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL
 SELECT 'rule',c.relname||'.'||r.rulename,
   jsonb_build_array(pg_get_ruledef(r.oid,true),r.ev_enabled)::text
 FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
) definitions ORDER BY kind,name,definition
"""


async def catalog_digest(c):
    rows = [tuple(r.values()) for r in await c.fetch(CATALOG_SQL)]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


async def verify_schema(c):
    """Trusted preparation and runtime share exactly the same postcondition."""
    # A predictable source hash is not an issuer credential. Only the database
    # owner may own/write the seal and migration registry, including column ACLs.
    # The owner/admin remains trusted and can change these facts after this read.
    unsafe_issuer = await c.fetchval("""SELECT EXISTS(
      SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname IN ('grid_schema_contract','schema_migrations')
        AND (c.relowner<>(SELECT datdba FROM pg_database WHERE datname=current_database())
          OR EXISTS(SELECT 1 FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
            WHERE a.grantee<>c.relowner AND a.privilege_type<>'SELECT')
          OR EXISTS(SELECT 1 FROM pg_attribute att CROSS JOIN LATERAL aclexplode(att.attacl) a
            WHERE att.attrelid=c.oid AND NOT att.attisdropped
              AND a.grantee<>c.relowner AND a.privilege_type<>'SELECT')))
    """)
    if unsafe_issuer is not False:
        raise SchemaBlocked('SCHEMA_METADATA_ISSUER_UNTRUSTED')
    seal = await c.fetchrow('SELECT version,source_sha256,catalog_sha256 FROM public.grid_schema_contract WHERE singleton')
    if not seal or seal['version'] != CONTRACT_VERSION or seal['source_sha256'] != source_digest():
        raise SchemaBlocked('SCHEMA_CONTRACT_SOURCE_MISMATCH')
    rows = await c.fetch('SELECT version,name FROM public.schema_migrations ORDER BY version')
    if [(r['version'],r['name']) for r in rows] != [(v,n) for v,n,_ in MIGRATIONS]:
        raise SchemaBlocked('SCHEMA_REGISTRY_MISMATCH')
    if not await model_registry_index_ready(c):
        raise SchemaBlocked('SCHEMA_INDEX48_MISMATCH')
    if await catalog_digest(c) != seal['catalog_sha256']:
        raise SchemaBlocked('SCHEMA_STRUCTURE_MISMATCH')
    state = await c.fetchval('SELECT state FROM public.grid_runtime_state WHERE singleton')
    from .runtime_gate import VALID_STATES
    if state not in VALID_STATES:
        raise SchemaBlocked('SCHEMA_RUNTIME_GATE_MISSING')


async def verify_runtime_schema(pool):
    async with pool.acquire() as c:
        async with c.transaction(isolation='repeatable_read', readonly=True):
            await c.execute('SET LOCAL search_path=pg_catalog,public')
            unsafe = await c.fetchval("""SELECT
              session_user<>current_user OR
              (SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
                 FROM pg_roles WHERE rolname=current_user)
              OR EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname<>current_user
                        AND pg_has_role(current_user,r.oid,'MEMBER'))
              OR has_database_privilege(current_user,current_database(),'CREATE,TEMP')
              OR EXISTS(SELECT 1 FROM pg_namespace WHERE substr(nspname,1,3)<>'pg_'
                        AND nspname<>'information_schema'
                        AND has_schema_privilege(current_user,oid,'CREATE'))
              OR EXISTS(SELECT 1 FROM pg_database WHERE datname=current_database()
                        AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user))
              OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname='public' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user))
              OR EXISTS(SELECT 1 FROM pg_shdepend d WHERE d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
                        AND d.refclassid='pg_authid'::regclass AND d.deptype='o'
                        AND d.refobjid=(SELECT oid FROM pg_roles WHERE rolname=current_user))
              OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE substr(n.nspname,1,3)<>'pg_' AND n.nspname<>'information_schema'
                          AND c.relkind IN ('r','p','v','m','f')
                          AND (has_table_privilege(current_user,c.oid,'TRIGGER,TRUNCATE,REFERENCES,MAINTAIN')
                            OR has_any_column_privilege(current_user,c.oid,'REFERENCES')))
              OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE substr(n.nspname,1,3)<>'pg_' AND n.nspname<>'information_schema' AND c.relkind='S'
                          AND has_sequence_privilege(current_user,c.oid,'UPDATE'))
              OR EXISTS(SELECT 1 FROM pg_parameter_acl p CROSS JOIN LATERAL aclexplode(p.paracl) a
                        WHERE a.grantee IN (0,(SELECT oid FROM pg_roles WHERE rolname=current_user)))
              OR current_setting('session_replication_role')<>'origin'
              OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                        WHERE p.prosecdef AND substr(n.nspname,1,3)<>'pg_'
                          AND n.nspname<>'information_schema'
                          AND has_function_privilege(current_user,p.oid,'EXECUTE'))
            """)
            if unsafe is not False:
                raise SchemaBlocked('RUNTIME_DDL_AUTHORITY_FORBIDDEN')
            for table in ('grid_schema_contract', 'schema_migrations'):
                writable = await c.fetchval("""SELECT
                  has_table_privilege(current_user,$1,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                  OR has_any_column_privilege(current_user,$1,'INSERT,UPDATE,REFERENCES')""", 'public.'+table)
                if writable is not False:
                    raise SchemaBlocked('RUNTIME_SCHEMA_METADATA_WRITABLE')
            missing = await c.fetchval("""SELECT EXISTS(
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) privilege
                WHERE n.nspname='public' AND c.relkind IN ('r','p')
                  AND c.relname NOT IN ('grid_schema_contract','schema_migrations')
                  AND NOT has_table_privilege(current_user,c.oid,privilege))
                OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                  WHERE n.nspname='public' AND c.relkind='S'
                    AND NOT has_sequence_privilege(current_user,c.oid,'USAGE'))
            """)
            if missing is not False:
                raise SchemaBlocked('RUNTIME_DML_GRANTS_MISSING')
            await verify_schema(c)
