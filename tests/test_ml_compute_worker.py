from pathlib import Path
import pytest
from grid.ml_compute_entry import train_job


def test_compute_worker_uses_fixed_module_not_payload_command():
    s=Path("grid/ml_compute_worker.py").read_text(encoding="utf-8")
    assert '[sys.executable,"-m","grid.ml_compute_entry"' in s
    assert "create_subprocess_shell" not in s
    assert "run_supervised_process" in s
    assert "run_with_lease" in s


def test_payload_cannot_raise_hard_limits():
    s=Path("grid/ml_compute_worker.py").read_text(encoding="utf-8")
    assert "min(int(payload.get(\"timeout_seconds\"" in s
    assert "min(int(payload.get(\"ram_limit_mb\"" in s


def test_entrypoint_whitelists_boost_backend():
    s=Path("grid/ml_compute_entry.py").read_text(encoding="utf-8")
    assert '("xgboost","lightgbm")' in s
    assert "unsupported ML backend" in s
    assert 'job.get("job_type")!="train"' in s
