"""Shared read-only index postcondition for migration and commissioning (PG16)."""


async def model_registry_index_ready(c):
    # IF NOT EXISTS alone does not establish that a same-name index is correct.
    # dataset_id is UUID: built-in uuid_ops, no collation, ASC/NULLS LAST (bits 0).
    # Strictly reject explicit storage/opclass options; the reviewed DDL has none.
    # Tablespace, owner, statistics and CLUSTER history are operational properties,
    # not the lookup definition; indcheckxmin is transient MVCC state, not DDL.
    row = await c.fetchrow("""SELECT i.indisvalid AS is_valid, i.indisready AS is_ready,
        i.indislive AS is_live, i.indisunique AS is_unique,
        i.indisprimary AS is_primary, i.indisexclusion AS is_exclusion,
        i.indnullsnotdistinct AS nulls_not_distinct,
        i.indpred IS NULL AS not_partial, i.indexprs IS NULL AS no_expressions,
        i.indnkeyatts AS keys, i.indnatts AS attributes,
        tn.nspname AS table_schema, t.relname AS table_name, am.amname AS method,
        idx.relkind::text AS index_kind, t.relkind::text AS table_kind,
        idx.relpersistence::text AS index_persistence, t.relpersistence::text AS table_persistence,
        idx.reloptions IS NULL AS no_storage_options,
        ia.attoptions IS NULL AS no_opclass_options,
        (a.atttypid='pg_catalog.uuid'::pg_catalog.regtype
         AND ia.atttypid='pg_catalog.uuid'::pg_catalog.regtype) AS key_type_is_uuid,
        i.indcollation[0] AS collation_oid, i.indoption[0] AS key_options,
        i.indclass[0] = (SELECT op.oid FROM pg_catalog.pg_opclass op
            JOIN pg_catalog.pg_namespace ons ON ons.oid=op.opcnamespace
            WHERE ons.nspname='pg_catalog' AND op.opcname='uuid_ops'
              AND op.opcmethod=idx.relam AND op.opcdefault
              AND op.opcintype='pg_catalog.uuid'::pg_catalog.regtype) AS opclass_is_builtin_uuid,
        ARRAY(SELECT ca.attname::text FROM pg_catalog.unnest(i.indkey) WITH ORDINALITY AS k(attnum,ord)
              JOIN pg_catalog.pg_attribute ca ON ca.attrelid=t.oid AND ca.attnum=k.attnum
              ORDER BY k.ord) AS columns
        FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class idx ON idx.oid=i.indexrelid
        JOIN pg_catalog.pg_namespace ns ON ns.oid=idx.relnamespace
        JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
        JOIN pg_catalog.pg_namespace tn ON tn.oid=t.relnamespace
        JOIN pg_catalog.pg_am am ON am.oid=idx.relam
        JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid AND a.attnum=i.indkey[0]
        JOIN pg_catalog.pg_attribute ia ON ia.attrelid=idx.oid AND ia.attnum=1
        WHERE ns.nspname='public' AND idx.relname='idx_model_registry_dataset_id'""")
    return row is not None and dict(row) == {
        'is_valid': True, 'is_ready': True, 'is_live': True, 'is_unique': False,
        'is_primary': False, 'is_exclusion': False, 'nulls_not_distinct': False,
        'not_partial': True, 'no_expressions': True, 'keys': 1, 'attributes': 1,
        'table_schema': 'public', 'table_name': 'model_registry', 'method': 'btree',
        'columns': ['dataset_id'], 'index_kind': 'i', 'table_kind': 'r',
        'index_persistence': 'p', 'table_persistence': 'p',
        'no_storage_options': True, 'no_opclass_options': True, 'key_type_is_uuid': True,
        'collation_oid': 0, 'key_options': 0, 'opclass_is_builtin_uuid': True}
