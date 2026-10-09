import asyncio
import pytest
from grid.ml_evaluation_pipeline import _finite_number, apply_evaluation_gate


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), None, "invalid"])
def test_nonfinite_or_malformed_evaluation_metric_fails_closed(value):
    assert _finite_number(value) != _finite_number(value)


def test_finite_evaluation_metric_is_preserved():
    assert _finite_number(1.25) == 1.25


def test_unsupported_stage_rejected_before_db_access():
    class Pool:
        async def fetchrow(self, *args):
            raise AssertionError("database must not be queried")
    with pytest.raises(ValueError, match="unsupported"):
        asyncio.run(apply_evaluation_gate(Pool(), "model", "TRAIN", {}))
