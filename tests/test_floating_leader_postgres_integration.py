"""Real PostgreSQL election race: only one node may win an empty lease."""
import asyncio
import json
import os
import uuid

import asyncpg
import pytest

from grid.floating_leader import FloatingLeader

DSN = os.environ.get("POSTGRES_DSN")


@pytest.mark.skipif(not DSN, reason="POSTGRES_DSN not configured")
def test_simultaneous_initial_campaign_has_single_winner():
    async def run():
        schema = "leader_ci_" + uuid.uuid4().hex[:16]
        admin = await asyncpg.connect(DSN)
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
        finally:
            await admin.close()
        pool = None
        try:
            pool = await asyncpg.create_pool(
                DSN, min_size=2, max_size=4,
                server_settings={"search_path": f'"{schema}",public'},
            )
            async with pool.acquire() as conn:
                await conn.execute(
                    "CREATE TABLE service_leases("
                    "service_key text PRIMARY KEY, owner text NOT NULL, "
                    "lease_until timestamptz NOT NULL, "
                    "heartbeat_at timestamptz NOT NULL DEFAULT now(), "
                    "metadata jsonb NOT NULL DEFAULT '{}'::jsonb)"
                )
            a = FloatingLeader(pool, node_id="node-a", lease_seconds=30)
            b = FloatingLeader(pool, node_id="node-b", lease_seconds=30)
            results = await asyncio.wait_for(
                asyncio.gather(a.campaign(), b.campaign()), timeout=10
            )
            assert sum(results) == 1, results
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT owner, metadata FROM service_leases "
                    "WHERE service_key='control-plane-leader'"
                )
            assert row["owner"] in {"node-a", "node-b"}
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            assert int(metadata["epoch"]) == 1
            assert (a.is_leader, b.is_leader) == tuple(results)
            # Expire the winner's lease and force a takeover. The previous
            # owner must not be able to renew with its stale fencing epoch.
            winner = a if a.is_leader else b
            challenger = b if a.is_leader else a
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE service_leases SET lease_until=now()-interval '1 second' "
                    "WHERE service_key='control-plane-leader'"
                )
            assert await challenger.campaign() is True
            assert challenger.epoch == 2
            assert await winner.renew() is False
            assert winner.is_leader is False
            assert await challenger.renew() is True
            async with pool.acquire() as conn:
                final = await conn.fetchrow(
                    "SELECT owner, metadata FROM service_leases "
                    "WHERE service_key='control-plane-leader'"
                )
            assert final["owner"] == challenger.node_id
            final_metadata = final["metadata"]
            if isinstance(final_metadata, str):
                final_metadata = json.loads(final_metadata)
            assert int(final_metadata["epoch"]) == 2
        finally:
            if pool is not None:
                await pool.close()
            admin = await asyncpg.connect(DSN)
            try:
                await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            finally:
                await admin.close()
    asyncio.run(run())
