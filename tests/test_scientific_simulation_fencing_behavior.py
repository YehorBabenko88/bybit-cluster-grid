import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from grid.scientific_simulation_gate import ScientificSimulationGate


class FakeConnection:
    def __init__(self, owns_attempt):
        self.owns_attempt = owns_attempt
        self.writes = []

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchval(self, query, *args):
        assert "attempt_id=$2 FOR UPDATE" in query
        return args[0] if self.owns_attempt else None

    async def execute(self, query, *args):
        self.writes.append(query)


class FakePool:
    def __init__(self, owns_attempt):
        self.connection = FakeConnection(owns_attempt)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


async def attempt_to_write(owns_attempt):
    pool = FakePool(owns_attempt)
    run_id, attempt_id = uuid4(), uuid4()
    async with pool.acquire() as conn:
        async with conn.transaction():
            owner = await conn.fetchval(
                """SELECT id FROM scientific_simulation_runs
                WHERE id=$1 AND status='RUNNING' AND attempt_id=$2 FOR UPDATE""",
                run_id, attempt_id)
            if owner is None:
                return "SKIPPED_STALE_ATTEMPT", conn.writes
            await conn.execute("DELETE FROM scientific_simulation_trades WHERE run_id=$1", run_id)
            return "OWNER", conn.writes


def test_stale_owner_cannot_write():
    result, writes = asyncio.run(attempt_to_write(False))
    assert result == "SKIPPED_STALE_ATTEMPT"
    assert writes == []


def test_current_owner_can_write():
    result, writes = asyncio.run(attempt_to_write(True))
    assert result == "OWNER"
    assert len(writes) == 1
