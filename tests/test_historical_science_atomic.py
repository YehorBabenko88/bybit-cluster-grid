import asyncio
import copy
import hashlib
from contextlib import asynccontextmanager

import pytest

from grid.historical_science_import import canonical_payload, import_historical_science


def bundle():
    value = {
        "schema": 1, "source": "strattester", "created_at": 1.0,
        "research_scope": "HISTORICAL_BOOTSTRAP_ONLY",
        "capabilities": {"candles": True, "open_interest": True,
                         "public_trade_aggregates": True},
        "symbols": [{"symbol": "BTCUSDT", "samples": 2},
                    {"symbol": "ETHUSDT", "samples": 3}],
    }
    value["sha256"] = hashlib.sha256(canonical_payload(value).encode()).hexdigest()
    return value


class MemoryDatabase:
    """External persistence boundary with commit/rollback semantics."""
    def __init__(self, failure):
        self.rows = {}
        self.failure = failure

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        before = copy.deepcopy(self.rows)
        try:
            yield
        except BaseException:
            self.rows = before
            raise

    async def fetchrow(self, sql, *args):
        assert "historical_scientific_bundles" in sql
        digest = args[2]
        if digest not in self.rows:
            self.rows[digest] = {"id": args[0], "symbols": {}}
        return {"id": self.rows[digest]["id"], "status": "IMPORTED"}

    async def execute(self, sql, *args):
        assert "historical_scientific_symbol_state" in sql
        if args[1] == "ETHUSDT" and self.failure:
            raise self.failure
        row = next(row for row in self.rows.values() if row["id"] == args[0])
        row["symbols"][args[1]] = args[3]


@pytest.mark.parametrize("failure", [ConnectionError("connection lost"),
                                      asyncio.CancelledError()])
def test_failed_or_cancelled_import_leaves_no_partial_bundle(failure):
    async def scenario():
        db = MemoryDatabase(failure)
        value = bundle()
        with pytest.raises(type(failure)):
            await import_historical_science(db, value)
        assert db.rows == {}
        db.failure = None
        result = await import_historical_science(db, value)
        repeated = await import_historical_science(db, value)
        assert result["bundle_id"] == repeated["bundle_id"]
        assert len(db.rows) == 1
        assert db.rows[value["sha256"]]["symbols"] == {"BTCUSDT": 2, "ETHUSDT": 3}
        assert result["live_evidence_promoted"] is False

    asyncio.run(scenario())
