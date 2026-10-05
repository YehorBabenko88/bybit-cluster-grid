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
