"""Explicit read-only REPEATABLE READ transaction boundary for Grid export.

Caller supplies an already connected disposable or authorized read-only
connection. No SQL mutations or production export are performed here.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from .snapshot_pg_transaction import inspect_transaction


@asynccontextmanager
async def readonly_snapshot_transaction(connection, *, expected_database: str):
    transaction = connection.transaction(
        isolation="repeatable_read", readonly=True, deferrable=True)
    async with transaction:
        await inspect_transaction(
            connection, expected_database=expected_database)
        yield connection
