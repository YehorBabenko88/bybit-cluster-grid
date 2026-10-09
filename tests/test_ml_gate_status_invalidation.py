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
    assert any("EVALUATION_FAILED" in query for query, _ in pool.commands)


def test_successful_recheck_preserves_nonproduction_transition():
    pool = FakePool(_metrics(1))
    assert asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {})) is True
    assert any("status<>'PRODUCTION'" in query for query, _ in pool.commands)
    assert not any("EVALUATION_FAILED" in query for query, _ in pool.commands)
