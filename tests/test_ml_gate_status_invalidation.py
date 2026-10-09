import asyncio
from grid.ml_evaluation_pipeline import apply_evaluation_gate


class FakePool:
    def __init__(self, metrics):
        self.metrics = metrics
        self.commands = []

    def acquire(self):
        return self

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def fetchrow(self, query, *args):
        if "FOR UPDATE" in query:
            return {"id": "model", "dataset_id": "dataset", "feature_version": "v1", "status": "CANDIDATE"}
        if "FROM dataset_snapshots" in query:
            return {"status": "READY", "feature_version": "v1"}
        if "stage='OOS'" in query:
            return {"passed": True}
        return {"id": "evaluation", "metrics": self.metrics}

    async def fetchval(self, query, *args):
        return "ROBUSTNESS_PASSED"

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
    assert any("SET status='REJECTED'" in query for query, _ in pool.commands)
    assert any("UPDATE model_evaluations SET passed=false" in query and "ROBUSTNESS" in query
               for query, _ in pool.commands)


def test_successful_recheck_preserves_nonproduction_transition():
    pool = FakePool(_metrics(1))
    assert asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {})) is True
    assert any("status IN ('CANDIDATE','REJECTED','OOS_PASSED')" in query for query, _ in pool.commands)
    assert any("SET status='OOS_PASSED'" in query and "ROBUSTNESS_PASSED" in query
               for query, _ in pool.commands)
    assert not any("SET status='REJECTED'" in query for query, _ in pool.commands)
    assert any("UPDATE model_evaluations SET passed=false" in query and "ROBUSTNESS" in query
               for query, _ in pool.commands)


def test_robustness_requires_prior_oos_status():
    pool = FakePool(_metrics(1))
    pool.metrics["scenarios"] = {name: {"overall": {"trades": 150, "expectancy": 1}}
        for name in ("fees_x1_5", "slippage_x2", "execution_delay", "drop_10pct", "combined")}
    assert asyncio.run(apply_evaluation_gate(pool, "model", "ROBUSTNESS", {})) is True
    assert any("status IN ('OOS_PASSED','ROBUSTNESS_PASSED')" in query
               for query, _ in pool.commands)


def test_status_write_failure_propagates_through_transaction():
    class FailingPool(FakePool):
        def __init__(self, metrics):
            super().__init__(metrics)
            self.transaction_exited_with_error = False

        async def execute(self, query, *args):
            await super().execute(query, *args)
            if "UPDATE model_registry" in query:
                raise ConnectionError("simulated database failure")

        async def __aexit__(self, exc_type, exc, tb):
            self.transaction_exited_with_error = exc_type is ConnectionError
            return False

    pool = FailingPool(_metrics(1))
    try:
        asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {}))
    except ConnectionError:
        pass
    else:
        raise AssertionError("database failure must propagate")
    assert pool.transaction_exited_with_error


def test_robustness_gate_rejects_missing_oos_transition():
    class UnadvancedPool(FakePool):
        async def fetchval(self, query, *args):
            return "CANDIDATE"

    pool = UnadvancedPool(_metrics(1))
    pool.metrics["scenarios"] = {name: {"overall": {"trades": 150, "expectancy": 1}}
        for name in ("fees_x1_5", "slippage_x2", "execution_delay", "drop_10pct", "combined")}
    try:
        asyncio.run(apply_evaluation_gate(pool, "model", "ROBUSTNESS", {}))
    except ValueError as exc:
        assert "before OOS" in str(exc)
    else:
        raise AssertionError("missing OOS transition must fail closed")


def test_ml_gate_rejects_dataset_that_is_not_ready():
    class NotReadyPool(FakePool):
        async def fetchrow(self, query, *args):
            if "FROM dataset_snapshots" in query:
                return {"status": "BUILDING", "feature_version": "v1"}
            return await super().fetchrow(query, *args)

    pool = NotReadyPool(_metrics(1))
    try:
        asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {}))
    except ValueError as exc:
        assert "not READY" in str(exc)
    else:
        raise AssertionError("unready dataset must block ML approval")
    assert not pool.commands


def test_robustness_gate_rejects_missing_persisted_oos_pass():
    class MissingOOSPool(FakePool):
        async def fetchrow(self, query, *args):
            if "stage='OOS'" in query:
                return None
            return await super().fetchrow(query, *args)

    pool = MissingOOSPool(_metrics(1))
    pool.metrics["scenarios"] = {name: {"overall": {"trades": 150, "expectancy": 1}}
        for name in ("fees_x1_5", "slippage_x2", "execution_delay", "drop_10pct", "combined")}
    try:
        asyncio.run(apply_evaluation_gate(pool, "model", "ROBUSTNESS", {}))
    except ValueError as exc:
        assert "passing OOS" in str(exc)
    else:
        raise AssertionError("robustness must require persisted OOS evidence")


def test_production_model_gate_cannot_modify_evaluations():
    class ProductionPool(FakePool):
        async def fetchrow(self, query, *args):
            if "FOR UPDATE" in query:
                return {"id": "model", "dataset_id": "dataset",
                        "feature_version": "v1", "status": "PRODUCTION"}
            return await super().fetchrow(query, *args)

    for stage in ("OOS", "ROBUSTNESS"):
        pool = ProductionPool(_metrics(1))
        try:
            asyncio.run(apply_evaluation_gate(pool, "model", stage, {}))
        except ValueError as exc:
            assert "immutable" in str(exc)
        else:
            raise AssertionError("production evaluation must not be mutated")
        assert not pool.commands


def test_invalid_gate_requirements_fail_before_sql():
    bad = (
        {"min_trades": 0},
        {"min_trades": "1.5"},
        {"min_expectancy": float("nan")},
        {"min_stress_expectancy": float("inf")},
        {"min_positive_fraction": -0.1},
        {"min_positive_fraction": 1.1},
        {"max_drawdown": -1},
        {"max_drawdown": float("nan")},
    )
    for requirements in bad:
        pool = FakePool(_metrics(1))
        try:
            asyncio.run(apply_evaluation_gate(pool, "model", "OOS", requirements))
        except ValueError:
            pass
        else:
            raise AssertionError("invalid gate requirement accepted: "+repr(requirements))
        assert not pool.commands


def test_corrupted_statistics_cannot_pass_oos_gate():
    invalid = (
        ("trades", -1),
        ("trades", 150.5),
        ("trades", float("inf")),
        ("expectancy", float("nan")),
        ("expectancy", float("inf")),
        ("max_drawdown", -0.1),
        ("max_drawdown", float("nan")),
    )
    for field, value in invalid:
        metrics = _metrics(1)
        metrics["segments"]["overall"][field] = value
        pool = FakePool(metrics)
        assert asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {})) is False, (field, value)
    for fraction in (-0.01, 1.01, float("nan"), float("inf")):
        metrics = _metrics(1)
        metrics["stability"]["positive_fraction"] = fraction
        pool = FakePool(metrics)
        assert asyncio.run(apply_evaluation_gate(pool, "model", "OOS", {})) is False, fraction
