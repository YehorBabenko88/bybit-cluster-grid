import asyncio
import pytest

from grid.snapshot_pg_composite import inspect_export_source
from grid.snapshot_pg_identity import ClusterIdentityBlocked
from grid.snapshot_pg_transaction import TransactionAttestationBlocked


class FakeConnection:
    def __init__(self, *, identity="123", isolation="repeatable read", read_only="on"):
        self.identity = identity
        self.isolation = isolation
        self.read_only = read_only

    async def fetchrow(self, query):
        if "pg_control_system" in query:
            return {"system_identifier": self.identity}
        return {"database_name": "fixture_db", "isolation": self.isolation,
                "read_only": self.read_only, "backend_pid": 42}

    async def fetch(self, query, *args):
        assert "information_schema.columns" in query
        return [{"column_name": "symbol", "data_type": "text",
                 "is_nullable": "NO"}]


def inspect(connection):
    return asyncio.run(inspect_export_source(
        connection, expected_database="fixture_db",
        expected_system_identifier="123", schema="public", table="candles_1m"))


def test_composite_stays_blocked_with_valid_connection():
    result = inspect(FakeConnection())
    assert result["status"] == "BLOCKED"
    assert result["export_authorized"] is False
    assert "available_ns" in result["catalog"]["missing_provenance"]


def test_wrong_cluster_rejected():
    with pytest.raises(ClusterIdentityBlocked):
        inspect(FakeConnection(identity="999"))


@pytest.mark.parametrize("changes", [
    {"isolation": "read committed"}, {"read_only": "off"},
])
def test_unsafe_transaction_rejected(changes):
    with pytest.raises(TransactionAttestationBlocked):
        inspect(FakeConnection(**changes))
