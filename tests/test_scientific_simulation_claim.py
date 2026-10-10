"""Regression coverage for atomic scientific simulation claims."""
import asyncio
import uuid

from grid.scientific_simulation_gate import ScientificSimulationGate


class AlreadyClaimedPool:
    def __init__(self):
        self.calls = []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        assert "RETURNING id" in query
        assert "status='QUEUED'" in query
        return None

    async def execute(self, *args):
        raise AssertionError("An unclaimed run must not mutate simulation state")

    async def fetchrow(self, *args):
        raise AssertionError("An unclaimed run must not read hypothesis state")

    async def fetch(self, *args):
        raise AssertionError("An unclaimed run must not query outcomes")


def test_unclaimed_simulation_returns_without_processing():
    pool = AlreadyClaimedPool()
    run_id = uuid.uuid4()
    hypothesis_id = uuid.uuid4()
    cutoff = "2026-10-01T00:00:00Z"
    result = asyncio.run(
        ScientificSimulationGate(pool).run_one(run_id, hypothesis_id, cutoff)
    )
    assert result["status"] == "NOT_CLAIMED"
    assert result["run_id"] == str(run_id)
    assert len(pool.calls) == 1
    assert pool.calls[0][2] == (run_id, hypothesis_id, cutoff)
