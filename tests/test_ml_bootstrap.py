from pathlib import Path


def test_ml_requirements_include_both_tree_backends():
    req=Path("requirements-ml.txt").read_text(encoding="utf-8").lower()
    assert "xgboost" in req
    assert "lightgbm" in req
    assert "scikit-learn" in req


def test_ml_bootstrap_is_role_aware_and_repairable():
    s=Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert '$Mode -in @("CONTROL","PILOT")' in s
    assert "ml-requirements.sha256" in s
    assert "ml-bootstrap.json" in s
    assert '--retries 8 --timeout 60 --prefer-binary' in s
    assert "import numpy,scipy,sklearn,joblib,xgboost,lightgbm" in s
    assert "XGBRegressor" in s
    assert "LGBMRegressor" in s
    assert 'status="failed"' in s


def test_main_bootstrap_invokes_ml_bootstrap_and_auto_pilot_rechecks():
    s=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert s.count("bootstrap-ml.ps1")>=2
    assert 'if($AgentMode -eq "PILOT")' in s
    assert "Grid ML runtime bootstrap failed" in s


def test_nodes_advertise_ml_runtime_and_dispatcher_requires_it():
    resources=Path("grid/resources.py").read_text(encoding="utf-8")
    dispatcher=Path("grid/ml_dispatcher.py").read_text(encoding="utf-8")
    assert '"ml_runtime_ready":ml_runtime_ready()' in resources
    assert 'if candidate["job_type"] in ("train","evaluate")' in dispatcher
    assert 'v.get("ml_runtime_ready") is True' in dispatcher


def test_install_state_persists_authorized_mode_separately_from_repair_kind():
    script = Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert 'authorized_agent_mode=$AgentMode' in script
    assert 'mode=$Mode;status="installed"' in script
    assert 'if($Enrollment.install_mode -notin @("PILOT","NORMAL"))' in script


def test_ml_bootstrap_recreates_missing_ready_journal_without_pip():
    script = Path("installer/bootstrap-ml.ps1").read_text(encoding="utf-8")
    assert 'if(!(Test-Path -LiteralPath $Python))' in script
    healthy = script.split('if(!$Need){', 1)[1].split('exit 0', 1)[0]
    assert 'status="ready"' in healthy
    assert 'Set-Content -Encoding UTF8 $Journal' in healthy
    assert '-m pip install' not in healthy
