"""Regression tests for retention bootstrap and empty-table backlog."""
import asyncio
import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock

from grid.retention_v2 import retention_backlog


def test_coordinator_bootstraps_retention_before_background_tasks():
    from grid import coordinator
    source = inspect.getsource(coordinator.start_leader_services)
    assert source.index("await ensure_retention_schema(db.pool)") < source.index("asyncio.create_task(maintenance_scheduler")
    assert source.index("await ensure_retention_schema(db.pool)") < source.index("asyncio.create_task(retention_scheduler")


def test_empty_retention_dataset_has_no_phantom_backlog():
    async def run():
        pool = type("Pool", (), {"fetchval": AsyncMock(return_value=False)})()
        result = await retention_backlog(pool, "market_events", 7)
        assert result == 0
        assert pool.fetchval.await_count == 1
        assert "SELECT EXISTS" in pool.fetchval.await_args.args[0]
    asyncio.run(run())


def test_existing_overdue_rows_keep_estimate():
    async def run():
        pool = type("Pool", (), {"fetchval": AsyncMock(side_effect=[
            True, [{"Plan": {"Plan Rows": 17}}]
        ])})()
        assert await retention_backlog(pool, "market_events", 7) == 17
        assert pool.fetchval.await_count == 2
    asyncio.run(run())


def test_existing_overdue_rows_never_report_zero():
    async def run():
        pool = type("Pool", (), {"fetchval": AsyncMock(side_effect=[
            True, [{"Plan": {"Plan Rows": 0}}]
        ])})()
        assert await retention_backlog(pool, "market_events", 7) == 1
    asyncio.run(run())
