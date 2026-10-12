import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from grid.scientific_simulation_gate import ScientificSimulationGate


class RestartPool:
    def __init__(self):
        self.run_id = uuid4()
        self.hypothesis_id = uuid4()
        self.cutoff = datetime.now(timezone.utc)
        self.started_at = datetime.now(timezone.utc) - timedelta(hours=25)
        self.status = "RUNNING"
        self.claims = 0

    async def fetch(self, sql, *args):
        assert "status='QUEUED'" in sql
        if self.status == "RUNNING" and self.started_at < datetime.now(timezone.utc) - timedelta(hours=24):
            return [{"id": self.run_id, "hypothesis_id": self.hypothesis_id, "dataset_cutoff": self.cutoff}]
        return []

    async def fetchval(self, sql, *args):
        if "RETURNING id" in sql:
            if self.status != "RUNNING" or self.started_at >= datetime.now(timezone.utc) - timedelta(hours=24):
                return None
            self.status = "RUNNING"
            self.started_at = datetime.now(timezone.utc)
            self.claims += 1
            return self.run_id
        if "max(dataset_cutoff)" in sql:
            return None
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "WAITING_OOS" in sql:
            self.status = "WAITING_OOS"
            return "UPDATE 1"
        raise AssertionError(sql)


def test_restart_reclaims_stale_run_once():
    pool = RestartPool()
    gate = ScientificSimulationGate(pool)
    result = asyncio.run(gate.run_queued())
    assert result[0]["status"] == "WAITING_OOS"
    assert pool.claims == 1
    assert asyncio.run(gate.run_queued()) == []
    assert pool.claims == 1


def test_recent_running_job_is_not_reclaimed():
    pool = RestartPool()
    pool.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert asyncio.run(ScientificSimulationGate(pool).run_queued()) == []
    assert pool.claims == 0
