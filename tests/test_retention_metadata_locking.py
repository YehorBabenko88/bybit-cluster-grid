import asyncio
from contextlib import asynccontextmanager

from grid.retention_v2 import cleanup_dataset_safe


class Connection:
    def __init__(self, required):
        self.required = required
        self.commands = []
        self.in_transaction = False

    @asynccontextmanager
    async def transaction(self):
        self.in_transaction = True
        try:
            yield self
        finally:
            self.in_transaction = False

    async def execute(self, sql, *args):
        self.commands.append((sql, self.in_transaction))
        if sql.startswith("LOCK TABLE"):
            return "LOCK TABLE"
        assert self.in_transaction
        return "DELETE 2"

    async def fetchval(self, sql, *args):
        assert self.in_transaction
        self.commands.append((sql, self.in_transaction))
        return self.required


class Pool:
    def __init__(self, required):
        self.connection = Connection(required)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_retention_refuses_deletion_without_required_consumers():
    pool = Pool(0)
    assert asyncio.run(cleanup_dataset_safe(pool, "candles_1m", 30)) == 0
    assert not any(sql.startswith("WITH safe") for sql, _ in pool.connection.commands)


def test_retention_locks_metadata_and_deletes_in_one_transaction():
    pool = Pool(1)
    assert asyncio.run(cleanup_dataset_safe(pool, "candles_1m", 30, max_batches=1)) == 2
    commands = pool.connection.commands
    assert commands[0][0].startswith("LOCK TABLE")
    assert "retention_holds" in commands[0][0]
    assert "retention_consumers" in commands[0][0]
    assert "consumer_watermarks" in commands[0][0]
    assert all(in_transaction for _, in_transaction in commands)
    assert commands[-1][0].startswith("WITH safe")
