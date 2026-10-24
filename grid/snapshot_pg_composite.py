"""Composite read-only PostgreSQL export preflight.

Even a successful cluster/transaction/catalog check cannot prove that
historical first-availability, revisions and source epochs exist. Therefore
the composite report remains BLOCKED until producer evidence is supplied.
"""
from __future__ import annotations

from .snapshot_pg_identity import verify_cluster_identity
from .snapshot_pg_transaction import inspect_transaction
from .snapshot_pg_preflight import inspect_pg_columns


async def inspect_export_source(
    connection, *, expected_database: str,
    expected_system_identifier: str,
    schema: str, table: str,
) -> dict:
    identity = await verify_cluster_identity(
        connection, expected_system_identifier=expected_system_identifier)
    transaction = await inspect_transaction(
        connection, expected_database=expected_database)
    catalog = await inspect_pg_columns(connection, schema=schema, table=table)
    return {
        "status": "BLOCKED",
        "identity": identity,
        "transaction": transaction,
        "catalog": catalog,
        "reason": "historical_availability_revisions_and_epoch_not_attested",
        "export_authorized": False,
    }
