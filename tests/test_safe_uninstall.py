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
