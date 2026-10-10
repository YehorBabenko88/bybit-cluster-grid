import asyncio
from contextlib import asynccontextmanager

import pytest

from grid.migrations import apply_migrations, MIGRATIONS


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append(sql)

    async def fetch(self, sql, *args):
        return self.rows

    @asynccontextmanager
    async def transaction(self):
        yield self


class Pool:
    def __init__(self, rows):
        self.connection = Connection(rows)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.mark.parametrize("rows", [
    [{"version": max(x[0] for x in MIGRATIONS) + 1, "name": "future"}],
    [{"version": MIGRATIONS[0][0], "name": "wrong_name"}],
])
def test_incompatible_migration_history_fails_closed(rows):
    async def run():
        pool = Pool(rows)
        with pytest.raises(RuntimeError):
            await apply_migrations(pool)
        assert not any(
            sql.lstrip().startswith("ALTER TABLE") for sql in pool.connection.executed
        )
        assert any("pg_advisory_unlock" in sql for sql in pool.connection.executed)

    asyncio.run(run())
