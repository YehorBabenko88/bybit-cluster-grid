"""PostgreSQL integration: transaction advisory locks serialize dispatchers."""
import asyncio
import os

import asyncpg
import pytest

from grid.ml_dispatcher import DISPATCH_LOCK_KEY


def test_dispatch_lock_serializes_and_releases_on_rollback():
    async def scenario():
        pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"], min_size=2, max_size=2)
        entered = asyncio.Event()
        release = asyncio.Event()
        acquired_second = asyncio.Event()

        async def first():
            async with pool.acquire() as conn:
                with pytest.raises(RuntimeError, match="forced rollback"):
                    async with conn.transaction():
                        await conn.execute("SELECT pg_advisory_xact_lock($1)", DISPATCH_LOCK_KEY)
                        entered.set()
                        await asyncio.wait_for(release.wait(), 5)
                        raise RuntimeError("forced rollback")

        async def second():
            await asyncio.wait_for(entered.wait(), 5)
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock($1)", DISPATCH_LOCK_KEY)
                    acquired_second.set()

        try:
            first_task = asyncio.create_task(first())
            await asyncio.wait_for(entered.wait(), 5)
            second_task = asyncio.create_task(second())
            await asyncio.sleep(0.15)
            assert not acquired_second.is_set(), "second dispatcher bypassed lock"
            release.set()
            await asyncio.wait_for(asyncio.gather(first_task, second_task), 5)
            assert acquired_second.is_set()
        finally:
            release.set()
            await pool.close()

    asyncio.run(scenario())
