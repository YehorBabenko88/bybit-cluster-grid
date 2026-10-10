import asyncio
from unittest.mock import AsyncMock

import pytest

from grid.worker import Worker
from grid.config import settings


@pytest.mark.asyncio
async def test_assignment_lease_tolerates_short_heartbeat_gap():
    worker = Worker()
    worker.last_assignment_heartbeat = 100.0
    worker.wanted = {"BTCUSDT"}
    worker.reconcile = AsyncMock()
    assert not await worker.expire_stale_assignments(
        now=100.0 + 3.0 * settings.heartbeat_seconds - 0.01
    )
    assert worker.wanted == {"BTCUSDT"}
    worker.reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_assignment_lease_revokes_stale_work():
    worker = Worker()
    worker.last_assignment_heartbeat = 100.0
    worker.wanted = {"BTCUSDT"}
    worker.micro_wanted = {"BTCUSDT"}
    worker.reconcile = AsyncMock()
    assert await worker.expire_stale_assignments(
        now=100.0 + max(1.0, 3.0 * settings.heartbeat_seconds)
    )
    assert worker.wanted == set()
    assert worker.micro_wanted == set()
    worker.reconcile.assert_awaited_once()


@pytest.mark.asyncio
async def test_assignment_lease_does_not_revoke_before_first_heartbeat():
    worker = Worker()
    worker.wanted = {"BTCUSDT"}
    worker.reconcile = AsyncMock()
    assert not await worker.expire_stale_assignments(now=100000.0)
    worker.reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_assignment_watchdog_runs_without_heartbeat_loop(monkeypatch):
    worker = Worker()
    called = asyncio.Event()

    async def expire(now=None):
        called.set()
        raise asyncio.CancelledError()

    worker.expire_stale_assignments = expire
    with pytest.raises(asyncio.CancelledError):
        await worker.assignment_watchdog()
    assert called.is_set()
