"""Retirement alone must never authorize deletion of recorded market history."""
import asyncio

import pytest

from grid.instrument_lifecycle import purge_retired


class RetiredHistoryPool:
    """In-memory SQL boundary; no actual database is used by these tests."""

    def __init__(self):
        self.history = {
            table: ["retained-source-record"]
            for table in (
                "market_events", "orderbook_snapshots", "derivatives_metrics",
                "footprint_1m", "candles_1m", "instruments",
            )
        }

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def fetch(self, sql, *args):
        return [{"symbol": "RETIRED_FIXTURE"}]

    async def fetchval(self, sql, *args):
        # No queued/running strategy is not a separate retention approval.
        return False

    async def execute(self, sql, *args):
        if sql.startswith("DELETE FROM "):
            self.history[sql.split()[2]].clear()
        else:
            raise AssertionError("Unexpected database mutation")


def test_retired_history_survives_without_separate_retention_approval():
    pool = RetiredHistoryPool()
    result = asyncio.run(purge_retired(pool))
    assert all(rows == ["retained-source-record"] for rows in pool.history.values())
    assert result == []


class UnavailablePool:
    def acquire(self):
        raise AssertionError("Automatic retirement cleanup must not access the database")


@pytest.mark.parametrize("kwargs", [{}, {"grace_days": 0}, {"grace_days": 365}])
def test_retired_cleanup_is_nondestructive_even_when_database_is_unavailable(kwargs):
    assert asyncio.run(purge_retired(UnavailablePool(), **kwargs)) == []
