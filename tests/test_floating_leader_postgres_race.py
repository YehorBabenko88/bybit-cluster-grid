"""Exercise real PostgreSQL uniqueness locking during simultaneous leader election."""
import asyncio
import os
import uuid

import asyncpg

from grid.floating_leader import FloatingLeader


def test_only_one_first_time_leader_postgres():
    async def scenario():
        schema = "leader_race_" + uuid.uuid4().hex
        admin = await asyncpg.connect(os.environ["POSTGRES_DSN"])
        pool = None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            await admin.execute(f"""CREATE TABLE "{schema}".service_leases (
                service_key text PRIMARY KEY,
                owner text NOT NULL,
                lease_until timestamptz NOT NULL,
                heartbeat_at timestamptz,
                metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb)""")

            async def init(conn):
                await conn.execute(f'SET search_path TO "{schema}"')

            pool = await asyncpg.create_pool(
                os.environ["POSTGRES_DSN"], min_size=2, max_size=4, setup=init
            )
            first = FloatingLeader(pool, node_id="node-a")
            second = FloatingLeader(pool, node_id="node-b")

            # Both attempts begin without a lease row. The unique index
            # serializes competing INSERTs; the live winner must not be stolen.
            won = await asyncio.wait_for(
                asyncio.gather(first.campaign(), second.campaign()), timeout=10
            )
            assert sorted(won) == [False, True]
            winner = first if won[0] else second
            loser = second if won[0] else first
            assert winner.is_leader and winner.epoch is not None
            assert not loser.is_leader and loser.epoch is None
            row = await pool.fetchrow(
                "SELECT owner, (metadata->>'epoch')::bigint AS epoch "
                "FROM service_leases WHERE service_key='control-plane-leader'"
            )
            assert row["owner"] == winner.node_id
            assert row["epoch"] == winner.epoch

            # No contender may steal an unexpired lease.
            assert await loser.campaign() is False

            # After expiry the loser may take over, with a higher epoch.
            await pool.execute(
                "UPDATE service_leases SET lease_until=now()-interval '1 second' "
                "WHERE service_key='control-plane-leader'"
            )
            assert await loser.campaign() is True
            assert loser.epoch > winner.epoch
            assert await winner.renew() is False
            assert winner.is_leader is False
            assert winner.epoch is None
        finally:
            if pool is not None:
                await pool.close()
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    asyncio.run(scenario())
