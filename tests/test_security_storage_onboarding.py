from pathlib import Path

def test_control_shared_token_auth_fails_closed_when_unset():
    src=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert 'if not configured:' in src
    assert 'CONTROL administrative authentication is not configured' in src
    assert 'constant_time_equal(token,configured)' in src

def test_node_credential_paths_remain_available_without_shared_token():
    src=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert 'if credential and await authenticate_agent(db.pool,node_id,credential):' in src
    assert 'await authenticate_agent(db.pool,x_node_id,x_node_credential)' in src

def test_agent_reports_local_storage_and_telegram_displays_it():
    resources=Path("grid/resources.py").read_text(encoding="utf-8")
    telegram=Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert '"grid_local_data_bytes"' in resources
    assert '("spool","spool")' in resources
    assert '("micro_spool","micro-spool")' in resources
    assert "agents are DB-less" in telegram
    assert "ml_artifacts_bytes" in telegram
    assert "strategy_cache_bytes" in telegram

def test_bootstrap_has_role_tags_and_network_preflight():
    bootstrap=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    check=Path("installer/verify-agent-network.ps1").read_text(encoding="utf-8")
    assert "tag:grid-control" in bootstrap
    assert "tag:grid-node" in bootstrap
    assert "verify-agent-network.ps1" in bootstrap
    assert "Test-NetConnection" in check
    assert "/health" in check
    assert "ESET" in check

def test_legacy_control_launcher_generates_admin_token_before_env_import():
    launcher=Path("installer/coordinator-launcher.ps1").read_text(encoding="utf-8")
    assert "'^GRID_SHARED_TOKEN=.+$'" in launcher
    assert "RandomNumberGenerator" in launcher
    assert 'Add-Content -Encoding UTF8 $EnvFile ("GRID_SHARED_TOKEN="+$token)' in launcher
