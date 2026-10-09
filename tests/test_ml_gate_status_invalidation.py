import asyncio
from grid.ml_evaluation_pipeline import apply_evaluation_gate


class FakePool:
    def __init__(self, metrics):
        self.metrics = metrics
        self.commands = []

    async def fetchrow(self, *args):
        return {"id": "evaluation", "metrics": self.metrics}

    async def execute(self, query, *args):
        self.commands.append((query, args))


def _metrics(expectancy):
    return {
        "segments": {"overall": {"trades": 150, "expectancy": expectancy, "max_drawdown": 0.1}},
        "stability": {"positive_fraction": 0.9},
    }


def test_failed_recheck_revokes_stale_preproduction_status():
    pool = FakePool(_metrics(-1))
    assert asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {})) is False
    assert any("REJECTED" in query for query, _ in pool.commands)


def test_successful_recheck_preserves_nonproduction_transition():
    pool = FakePool(_metrics(1))
    assert asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {})) is True
    assert any("status IN ('CANDIDATE','REJECTED','OOS_PASSED')" in query for query, _ in pool.commands)
    assert not any("SET status='REJECTED'" in query for query, _ in pool.commands)


def test_robustness_requires_prior_oos_status():
    pool = FakePool(_metrics(1))
    pool.metrics["scenarios"] = {name: {"overall": {"trades": 150, "expectancy": 1}}
        for name in ("fees_x1_5", "slippage_x2", "execution_delay", "drop_10pct", "combined")}
    assert asyncio.run(apply_evaluation_gate(pool, "model", "ROBUSTNESS", {})) is True
    assert any("status IN ('OOS_PASSED','ROBUSTNESS_PASSED')" in query
               for query, _ in pool.commands)
