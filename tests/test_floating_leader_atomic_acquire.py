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


def test_malformed_lease_epochs_fail_closed():
    async def scenario(metadata):
        class BadEpochConnection(Connection):
            async def fetchrow(self, sql):
                return {"owner": "old", "lease_until": None, "metadata": metadata}

        pool = Pool(1)
        pool.connection = BadEpochConnection(1)
        leader = FloatingLeader(pool, node_id="candidate")
        try:
            await leader.campaign()
        except ValueError as exc:
            assert "invalid leader lease epoch" in str(exc)
        else:
            raise AssertionError("malformed lease epoch must not allow leadership")
        assert not leader.is_leader and leader.epoch is None
        assert pool.connection.insert_sql is None

    for metadata in ('{"epoch":-1}', '{"epoch":true}', '{"epoch":"42"}',
                     '{"epoch":1.5}', '{"epoch":null}'):
        asyncio.run(scenario(metadata))


def test_live_competitor_lease_clears_stale_local_epoch():
    from datetime import datetime, timedelta, timezone

    async def scenario():
        class LiveLeaseConnection(Connection):
            async def fetchrow(self, sql):
                return {
                    "owner": "other",
                    "lease_until": datetime.now(timezone.utc) + timedelta(minutes=5),
                    "metadata": '{"epoch":99}',
                }

            async def fetchval(self, sql, *args):
                assert sql == "SELECT now()"
                return datetime.now(timezone.utc)

        pool = Pool(1)
        pool.connection = LiveLeaseConnection(1)
        leader = FloatingLeader(pool, node_id="stale")
        leader.is_leader = True
        leader.epoch = 10
        assert await leader.campaign() is False
        assert leader.is_leader is False
        assert leader.epoch is None
        assert pool.connection.insert_sql is None

    asyncio.run(scenario())


def test_bigint_epoch_overflow_fails_before_insert():
    async def scenario():
        class OverflowConnection(Connection):
            async def fetchrow(self, sql):
                return {"owner": "old", "lease_until": None,
                        "metadata": '{"epoch":9223372036854775807}'}

        pool = Pool(1)
        pool.connection = OverflowConnection(1)
        leader = FloatingLeader(pool, node_id="candidate")
        try:
            await leader.campaign()
        except ValueError as exc:
            assert "bigint range" in str(exc)
        else:
            raise AssertionError("exhausted bigint epoch must not be acquired")
        assert leader.is_leader is False and leader.epoch is None
        assert pool.connection.insert_sql is None

    asyncio.run(scenario())
