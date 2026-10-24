import asyncio
import pytest

from grid.snapshot_pg_transaction import (
    TransactionAttestationBlocked, inspect_transaction,
)


class Connection:
    def __init__(self, **changes):
        self.values = dict(database_name="disposable_grid",
                           isolation="repeatable read", read_only="on",
                           backend_pid=123)
        self.values.update(changes)

    async def fetchrow(self, query):
        assert "current_database()" in query
        assert "transaction_read_only" in query
        return self.values


def test_read_only_repeatable_read_pass():
    result = asyncio.run(inspect_transaction(
        Connection(), expected_database="disposable_grid"))
    assert result["status"] == "TRANSACTION_MODE_PASS"
    assert result["source_coherence_attested"] is False


@pytest.mark.parametrize("changes", [
    {"isolation": "read committed"}, {"read_only": "off"},
    {"database_name": "production"}, {"backend_pid": 0},
])
def test_unsafe_transaction_rejected(changes):
    with pytest.raises(TransactionAttestationBlocked):
        asyncio.run(inspect_transaction(
            Connection(**changes), expected_database="disposable_grid"))
