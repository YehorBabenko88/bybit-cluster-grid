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


def test_coordinator_closes_database_pool_on_shutdown():
    s=Path("grid/coordinator.py").read_text(encoding="utf-8")
    shutdown=s.split('@app.on_event("shutdown")',1)[1]
    assert "await db.pool.close()" in shutdown
    assert "db.pool=None" in shutdown
