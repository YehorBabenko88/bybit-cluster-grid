import asyncio

from grid.floating_leader import FloatingLeader


class Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class Conn:
    def __init__(self, result):
        self.result = result
        self.sql = ""

    def transaction(self):
        return Tx()

    async def fetchrow(self, *args):
        return None

    async def fetchval(self, sql, *args):
        self.sql = sql
        return 123456 if self.result == "INSERT 0 1" else None

    async def execute(self, sql, *args):
        self.sql = sql
        return self.result


class Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        return False


class Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return Acquire(self.conn)


def test_concurrent_first_campaign_loser_does_not_claim_leadership():
    async def scenario():
        conn = Conn("INSERT 0 0")
        leader = FloatingLeader(Pool(conn), node_id="contender-b")
        assert not await leader.campaign()
        assert leader.is_leader is False
        assert leader.epoch is None
        assert "service_leases.lease_until IS NULL OR service_leases.lease_until <= now()" in conn.sql
        assert "RETURNING (metadata->>'epoch')::bigint" in conn.sql

    asyncio.run(scenario())


def test_first_campaign_winner_claims_leadership():
    async def scenario():
        conn = Conn("INSERT 0 1")
        leader = FloatingLeader(Pool(conn), node_id="contender-a")
        assert await leader.campaign()
        assert leader.is_leader is True
        assert isinstance(leader.epoch, int)

    asyncio.run(scenario())
