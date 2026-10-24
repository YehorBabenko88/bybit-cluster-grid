import asyncio
import pytest

from grid.snapshot_pg_readonly import readonly_snapshot_transaction
from grid.snapshot_pg_transaction import TransactionAttestationBlocked


class Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.active = True
        return self

    async def __aexit__(self, *args):
        self.connection.active = False


class Connection:
    def __init__(self, *, read_only="on"):
        self.active = False
        self.read_only = read_only
        self.options = None

    def transaction(self, **options):
        self.options = options
        return Transaction(self)

    async def fetchrow(self, query):
        assert self.active
        return {"database_name": "fixture_db", "isolation": "repeatable read",
                "read_only": self.read_only, "backend_pid": 42}


def test_transaction_scope():
    async def run():
        conn = Connection()
        async with readonly_snapshot_transaction(
                conn, expected_database="fixture_db"):
            assert conn.active
        assert not conn.active
        assert conn.options == dict(isolation="repeatable_read",
                                    readonly=True, deferrable=True)
    asyncio.run(run())


def test_invalid_mode_exits_transaction():
    async def run():
        conn = Connection(read_only="off")
        with pytest.raises(TransactionAttestationBlocked):
            async with readonly_snapshot_transaction(
                    conn, expected_database="fixture_db"):
                pass
        assert not conn.active
    asyncio.run(run())
