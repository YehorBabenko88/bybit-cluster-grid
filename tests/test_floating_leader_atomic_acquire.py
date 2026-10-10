import asyncio
from contextlib import asynccontextmanager

from grid.floating_leader import FloatingLeader


class Connection:
    def __init__(self, acquired):
        self.acquired = acquired
        self.insert_sql = None

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, sql):
        return None

    async def fetchval(self, sql, *args):
        if "INSERT INTO service_leases" in sql:
            self.insert_sql = sql
            return self.acquired
        raise AssertionError("unexpected SQL")


class Pool:
    def __init__(self, acquired):
        self.connection = Connection(acquired)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_concurrent_first_insert_loser_cannot_claim_leadership():
    async def scenario():
        pool = Pool(None)  # PostgreSQL ON CONFLICT ... WHERE rejected live lease
        leader = FloatingLeader(pool, node_id="loser")
        assert await leader.campaign() is False
        assert leader.is_leader is False
        assert leader.epoch is None
        sql = pool.connection.insert_sql
        assert "WHERE service_leases.lease_until <= now()" in sql
        assert "RETURNING (metadata->>'epoch')::bigint" in sql

    asyncio.run(scenario())


def test_successful_atomic_insert_publishes_leadership():
    async def scenario():
        pool = Pool(42)
        leader = FloatingLeader(pool, node_id="winner")
        assert await leader.campaign() is True
        assert leader.is_leader is True
        assert leader.epoch is not None

    asyncio.run(scenario())


def test_invalid_lease_metadata_fails_closed():
    async def scenario():
        class BadMetadataConnection(Connection):
            async def fetchrow(self, sql):
                return {"owner": "old", "lease_until": None, "metadata": '["invalid"]'}

        pool = Pool(1)
        pool.connection = BadMetadataConnection(1)
        leader = FloatingLeader(pool, node_id="candidate")
        try:
            await leader.campaign()
        except ValueError as exc:
            assert "expected object" in str(exc)
        else:
            raise AssertionError("invalid JSON metadata must not allow leadership")
        assert not leader.is_leader
        assert leader.epoch is None

    asyncio.run(scenario())
