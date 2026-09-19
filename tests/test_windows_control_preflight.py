from pathlib import Path

def test_control_port_is_consistent_everywhere():
    config=Path("grid/config.py").read_text(encoding="utf-8")
    run=Path("run_coordinator.py").read_text(encoding="utf-8")
    launcher=Path("installer/coordinator-launcher.ps1").read_text(encoding="utf-8")
    assert '127.0.0.1:8765' in config
    assert "port=8765" in run
    assert "--port 8765" in launcher

def test_windows_preflight_checks_role_entrypoint():
    text=Path("installer/preflight.ps1").read_text(encoding="utf-8")
    assert 'ValidateSet("CONTROL","PILOT","NORMAL")' in text
    assert "run_coordinator.py" in text
    assert "import grid.coordinator" in text

def test_bootstrap_repairs_role_but_preserves_env_secrets():
    text=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert "ROLE=$DesiredRole" in text
    assert "$lines=@(Get-Content $EnvFile" in text
    assert "POSTGRES_DSN" not in text.split("$lines=@(Get-Content $EnvFile",1)[1].split("# PostgreSQL",1)[0]


def test_external_control_postgres_is_not_claimed_as_grid_owned():
    text=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert '[string]$ExistingPostgresDsn=""' in text
    block=text.split("if($ExistingPostgresDsn){",1)[1].split("} else {",1)[0]
    assert "POSTGRES_DSN=$probe" in block
    assert "postgres-owned.json" not in block
    assert "provision_postgres.ps1" not in block

def test_legacy_handoff_is_staged_not_imported_before_start():
    text=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert 'status="STAGED"' in text
    assert 'import_allowed=$false' in text
    assert "Await explicit global START" in text
    assert "grid.legacy_bootstrap_import" not in text
