"""Read-only PostgreSQL export schema preflight.

The native Grid candle DDL does not currently prove availability/revision
history. This probe only queries catalog metadata and always fails closed
until the source-owned provenance contract is independently verified.
"""
from __future__ import annotations


REQUIRED_PROVENANCE = frozenset({
    "exchange", "market_type", "symbol", "event_ns", "ingest_ns",
    "available_ns", "watermark_ns", "revision", "producer",
    "source_epoch", "quality_status", "eligible", "complete",
})


class SourceSchemaBlocked(ValueError):
    pass


async def inspect_pg_columns(connection, *, schema: str, table: str) -> dict:
    if not schema or not table or not all(
        value.replace("_", "").isalnum() for value in (schema, table)
    ):
        raise SourceSchemaBlocked("Invalid catalog selector")
    rows = await connection.fetch(
        """SELECT column_name, data_type, is_nullable
           FROM information_schema.columns
           WHERE table_schema = $1 AND table_name = $2
           ORDER BY ordinal_position""",
        schema, table,
    )
    columns = {row["column_name"]: {
        "data_type": row["data_type"], "nullable": row["is_nullable"]
    } for row in rows}
    missing = sorted(REQUIRED_PROVENANCE - columns.keys())
    nullable = sorted(name for name in REQUIRED_PROVENANCE & columns.keys()
                      if columns[name]["nullable"] != "NO")
    expected_types = {
        "event_ns": {"bigint"}, "ingest_ns": {"bigint"},
        "available_ns": {"bigint"}, "watermark_ns": {"bigint"},
        "revision": {"integer", "bigint"},
        "eligible": {"boolean"}, "complete": {"boolean"},
    }
    wrong_types = sorted(name for name, allowed in expected_types.items()
                         if name in columns and columns[name]["data_type"] not in allowed)
    return {
        "status": "BLOCKED",
        "schema": schema,
        "table": table,
        "columns": columns,
        "missing_provenance": missing,
        "nullable_provenance": nullable,
        "wrong_type_provenance": wrong_types,
        "reason": "catalog_presence_does_not_attest_historical_provenance",
    }
