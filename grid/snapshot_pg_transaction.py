"""Read-only transaction identity checks for disposable PostgreSQL exporters.

Must run inside a caller-managed REPEATABLE READ READ ONLY transaction.
No connection settings or production data are modified by this module.
"""
from __future__ import annotations


class TransactionAttestationBlocked(ValueError):
    pass


async def inspect_transaction(connection, *, expected_database: str) -> dict:
    if type(expected_database) is not str or not expected_database:
        raise TransactionAttestationBlocked("Missing expected database")
    row = await connection.fetchrow(
        """SELECT current_database() AS database_name,
                  current_setting('transaction_isolation') AS isolation,
                  current_setting('transaction_read_only') AS read_only,
                  pg_backend_pid() AS backend_pid"""
    )
    if row is None:
        raise TransactionAttestationBlocked("Missing transaction identity")
    values = dict(row)
    if (values.get("database_name") != expected_database
            or values.get("isolation") != "repeatable read"
            or values.get("read_only") != "on"):
        raise TransactionAttestationBlocked("Unexpected database or transaction mode")
    pid = values.get("backend_pid")
    if type(pid) is not int or pid <= 0:
        raise TransactionAttestationBlocked("Invalid backend identity")
    return {"status": "TRANSACTION_MODE_PASS", "database_name": expected_database,
            "isolation": "repeatable read", "read_only": True,
            "backend_pid": pid, "source_coherence_attested": False}
