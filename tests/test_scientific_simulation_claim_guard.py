import asyncio
from uuid import uuid4

from grid.scientific_simulation_gate import ScientificSimulationGate


class RejectedClaimPool:
    def __init__(self):
        self.claims = 0
        self.reads = 0

    async def fetchval(self, sql, *args):
        if "RETURNING id" in sql and "status='QUEUED'" in sql:
            self.claims += 1
            return None
        self.reads += 1
        raise AssertionError("unclaimed simulation must not read evidence")


def test_unclaimed_simulation_does_not_process_evidence():
    pool = RejectedClaimPool()
    run_id = uuid4()
    result = asyncio.run(ScientificSimulationGate(pool).run_one(run_id, uuid4(), None))
    assert result == {"run_id": str(run_id), "status": "SKIPPED_NOT_QUEUED"}
    assert pool.claims == 1
    assert pool.reads == 0
