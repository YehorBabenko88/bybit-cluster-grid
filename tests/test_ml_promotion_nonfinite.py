import pytest
from grid.ml_promotion_gate import evaluate_gate


def _passing():
    return dict(samples=600, folds=5, profitable_folds=4,
                max_drawdown_pct=10, fee_stress_factor=2,
                symbol_count=4, leakage_check_passed=True)


def test_normal_metrics_pass():
    assert evaluate_gate(_passing())["passed"]


@pytest.mark.parametrize("key,bad", [
    ("samples", "nan"), ("folds", "infinity"),
    ("profitable_folds", None), ("max_drawdown_pct", float("nan")),
    ("max_drawdown_pct", float("-inf")),
    ("fee_stress_factor", float("inf")),
    ("symbol_count", "invalid"),
])
def test_invalid_metrics_fail_closed(key, bad):
    metrics = _passing()
    metrics[key] = bad
    assert not evaluate_gate(metrics)["passed"]
