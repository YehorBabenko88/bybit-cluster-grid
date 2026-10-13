from pathlib import Path


def test_scheduled_tasks_never_overlap_instances():
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    assert '$Settings.MultipleInstances="IgnoreNew"' in s


def test_control_launchers_wait_only_for_grid_owned_postgres():
    guard=Path("installer/wait-grid-postgres.ps1").read_text(encoding="utf-8")
    coord=Path("installer/coordinator-launcher.ps1").read_text(encoding="utf-8")
    archive=Path("installer/archive-launcher.ps1").read_text(encoding="utf-8")
    assert 'owned_by_grid -ne $true' in guard
    assert 'BybitClusterGridPostgres' in guard
    assert "Start-Service" in guard
    assert "wait-grid-postgres.ps1" in coord
    assert "wait-grid-postgres.ps1" in archive


def test_coordinator_closes_database_pool_on_shutdown(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from grid import coordinator
    async def run():
        raw=SimpleNamespace(close=AsyncMock())
        db=SimpleNamespace(pool=object(),raw_pool=raw)
        runtime=SimpleNamespace(stop=AsyncMock())
        monkeypatch.setattr(coordinator,'db',db)
        monkeypatch.setattr(coordinator,'control_runtime',runtime)
        await coordinator.shutdown()
        runtime.stop.assert_awaited_once()
        raw.close.assert_awaited_once()
        assert db.pool is None
    asyncio.run(run())
