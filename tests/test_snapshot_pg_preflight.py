import pytest
import asyncio

from grid.snapshot_pg_preflight import (
    REQUIRED_PROVENANCE, SourceSchemaBlocked, inspect_pg_columns,
)


class FakeConnection:
    def __init__(self, columns):
        self.columns = columns
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return [{"column_name": name, "data_type": "text",
                 "is_nullable": "NO"} for name in self.columns]


def test_missing_provenance_blocks():
    conn = FakeConnection({"symbol", "ts", "close"})
    result = asyncio.run(inspect_pg_columns(conn, schema="public", table="candles_1m"))
    assert result["status"] == "BLOCKED"
    assert "available_ns" in result["missing_provenance"]
    assert len(conn.calls) == 1
    assert "information_schema.columns" in conn.calls[0][0]


def test_even_full_columns_not_proof_of_history():
    conn = FakeConnection(REQUIRED_PROVENANCE)
    result = asyncio.run(inspect_pg_columns(conn, schema="public", table="candles_1m"))
    assert result["missing_provenance"] == []
    assert result["status"] == "BLOCKED"


def test_invalid_selector_never_queries():
    conn = FakeConnection(set())
    with pytest.raises(SourceSchemaBlocked):
        await inspect_pg_columns(conn, schema="public;DROP", table="candles_1m"))
    assert not conn.calls
