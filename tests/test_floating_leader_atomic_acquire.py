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
        assert "service_leases.lease_until IS NULL OR service_leases.lease_until <= now()" in sql
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


def test_leader_run_recovers_after_temporary_database_outage():
    async def scenario():
        class RecoveringLeader(FloatingLeader):
            def __init__(self):
                super().__init__(pool=None, node_id="recovery", renew_seconds=0.001)
                self.attempts = 0

            async def campaign(self):
                self.attempts += 1
                if self.attempts == 1:
                    raise ConnectionError("PostgreSQL temporarily unavailable")
                self.is_leader = True
                self.epoch = 123
                return True

            async def renew(self):
                self.stop()
                return True

        leader = RecoveringLeader()
        await asyncio.wait_for(leader.run(on_gain=record_gain), 2)

    async def record_gain(epoch):
        gained.append(epoch)

    gained = []
    asyncio.run(scenario())
    assert gained == [123]


def test_leader_run_calls_on_loss_after_renew_database_failure():
    async def scenario():
        events = []

        class FailingRenewLeader(FloatingLeader):
            def __init__(self):
                super().__init__(pool=None, node_id="failover", renew_seconds=0.001)
                self.attempts = 0

            async def campaign(self):
                self.attempts += 1
                if self.attempts == 1:
                    self.is_leader = True
                    self.epoch = 456
                    return True
                self.stop()
                return False

            async def renew(self):
                raise ConnectionError("PostgreSQL disconnected during renewal")

        async def on_gain(epoch):
            events.append(("gain", epoch))

        async def on_loss():
            events.append(("loss", None))

        leader = FailingRenewLeader()
        await asyncio.wait_for(leader.run(on_gain=on_gain, on_loss=on_loss), 2)
        assert events == [("gain", 456), ("loss", None)]
        assert leader.is_leader is False
        assert leader.epoch is None

    asyncio.run(scenario())


def test_invalid_leader_lease_intervals_are_rejected():
    import pytest

    for lease, renew in [
        (0, 1), (-1, 1), (20, 0), (20, -1),
        (20, 20), (20, 21), (20, float("nan")),
        (20, float("inf")), (20, float("-inf")),
    ]:
        with pytest.raises(ValueError, match="renew_seconds"):
            FloatingLeader(pool=None, lease_seconds=lease, renew_seconds=renew)

    leader = FloatingLeader(pool=None, lease_seconds=20, renew_seconds=5)
    assert leader.lease_seconds == 20
    assert leader.renew_seconds == 5


def test_failed_gain_callback_releases_its_epoch_and_retries():
    async def scenario():
        events = []

        class RetryingLeader(FloatingLeader):
            def __init__(self):
                super().__init__(pool=None, node_id="retry", renew_seconds=0.001)
                self.epochs = iter((101, 102))

            async def campaign(self):
                self.epoch = next(self.epochs)
                self.is_leader = True
                return True

            async def release(self, epoch):
                events.append(("release", epoch))
                return "UPDATE 1"

            async def renew(self):
                self.stop()
                return True

        async def on_gain(epoch):
            events.append(("gain", epoch))
            if epoch == 101:
                raise RuntimeError("startup failed")

        leader = RetryingLeader()
        await asyncio.wait_for(leader.run(on_gain=on_gain), 2)
        assert events == [("gain", 101), ("release", 101), ("gain", 102)]
        assert leader.epoch == 102

    asyncio.run(scenario())


def test_on_loss_failure_does_not_prevent_future_leader_election():
    async def scenario():
        events = []

        class Leader(FloatingLeader):
            def __init__(self):
                super().__init__(pool=None, node_id="recover-loss", renew_seconds=0.001)
                self.campaigns = 0

            async def campaign(self):
                self.campaigns += 1
                self.is_leader = True
                self.epoch = self.campaigns
                return True

            async def renew(self):
                if self.epoch == 1:
                    self.is_leader = False
                    self.epoch = None
                    return False
                self.stop()
                return True

        async def on_gain(epoch):
            events.append(("gain", epoch))

        async def on_loss():
            events.append(("loss", None))
            raise RuntimeError("cleanup failed")

        leader = Leader()
        await asyncio.wait_for(leader.run(on_gain=on_gain, on_loss=on_loss), 2)
        assert events == [("gain", 1), ("loss", None), ("gain", 2)]
        assert leader.epoch == 2

    asyncio.run(scenario())
