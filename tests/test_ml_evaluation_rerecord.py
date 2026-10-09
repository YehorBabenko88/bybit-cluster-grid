import asyncio
from unittest.mock import patch

from grid.ml_evaluation_pipeline import record_oos_evaluation, record_robustness_evaluation


class TransactionPool:
    def __init__(self):
        self.statements = []

    def acquire(self):
        return self

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetchrow(self, query, *args):
        self.statements.append(query)
        return {"id": "model"}

    async def execute(self, query, *args):
        self.statements.append(query)


def test_fresh_oos_invalidates_all_preproduction_gates():
    pool = TransactionPool()
    with patch("grid.ml_evaluation_pipeline.evaluate_trades", return_value={"overall": {}}), patch(
        "grid.ml_evaluation_pipeline.stability_summary", return_value={}
    ):
        asyncio.run(record_oos_evaluation(pool, "model", "dataset", []))
    assert any("FOR UPDATE" in query for query in pool.statements)
    assert any("SET status='REJECTED'" in query for query in pool.statements)


def test_fresh_robustness_requires_new_robustness_gate_but_keeps_oos():
    pool = TransactionPool()
    with patch("grid.ml_evaluation_pipeline.robustness_suite", return_value={}):
        asyncio.run(record_robustness_evaluation(pool, "model", "dataset", []))
    assert any("FOR UPDATE" in query for query in pool.statements)
    assert any("SET status='OOS_PASSED'" in query for query in pool.statements)
    assert not any("SET status='REJECTED'" in query for query in pool.statements)
