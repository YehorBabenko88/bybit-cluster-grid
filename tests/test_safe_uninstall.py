from pathlib import Path

def test_uninstall_uses_fixed_grid_service_and_root():
    text=Path("installer/uninstall.ps1").read_text(encoding="utf-8")
    assert "BybitClusterGridPostgres" in text
    assert "postgres-owned.json" in text
    assert "owned_by_grid" in text
    assert 'Join-Path $env:ProgramData "BybitClusterGrid"' in text

def test_agent_uses_powershell_purge_switch():
    text=Path("grid/agent_commands.py").read_text(encoding="utf-8")
    assert 'args.append("-PurgeData")' in text
    assert 'args.append("--purge-data")' not in text


def test_uninstall_removes_control_task_too():
    text=Path("installer/uninstall.ps1").read_text(encoding="utf-8")
    assert "BybitClusterGridCoordinator" in text
    assert "Unregister-ScheduledTask $CoordinatorTaskName" in text

def test_purge_stays_scoped_to_grid_owned_postgres():
    text=Path("installer/uninstall.ps1").read_text(encoding="utf-8")
    assert "owned_by_grid" in text
    assert "BybitClusterGridPostgres" in text
    assert "55432" in text
