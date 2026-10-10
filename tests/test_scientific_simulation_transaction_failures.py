import asyncio
from contextlib import asynccontextmanager

import pytest


class TransactionalMemoryConnection:
    def __init__(self, fail_at=None):
        self.rows = []
        self.status = "RUNNING"
        self.fail_at = fail_at
        self.calls = 0

    @asynccontextmanager
    async def transaction(self):
        snapshot = (list(self.rows), self.status)
        try:
            yield self
        except Exception:
            self.rows, self.status = snapshot
            raise

    async def execute(self, sql, *args):
        self.calls += 1
        if self.calls == self.fail_at:
            raise ConnectionError("simulated PostgreSQL connection loss")
        if sql.startswith("DELETE"):
            self.rows.clear()
        elif sql.startswith("INSERT"):
            self.rows.append(args[1])
        elif sql.startswith("UPDATE"):
            self.status = "SIMULATION_PASSED"


async def persist(conn):
    async with conn.transaction():
        await conn.execute("DELETE FROM scientific_simulation_trades WHERE run_id=$1", "run")
        for ordinal in range(3):
            await conn.execute("INSERT INTO scientific_simulation_trades VALUES(...)", "run", ordinal)
        await conn.execute("UPDATE scientific_simulation_runs SET status=$2", "run")


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5])
def test_transaction_rolls_back_if_any_write_fails(fail_at):
    conn = TransactionalMemoryConnection(fail_at=fail_at)
    conn.rows = ["previous"]
    with pytest.raises(ConnectionError):
        asyncio.run(persist(conn))
    assert conn.rows == ["previous"]
    assert conn.status == "RUNNING"


def test_successful_transaction_replaces_old_rows_and_marks_complete():
    conn = TransactionalMemoryConnection()
    conn.rows = ["previous"]
    asyncio.run(persist(conn))
    assert conn.rows == [0, 1, 2]
    assert conn.status == "SIMULATION_PASSED"
