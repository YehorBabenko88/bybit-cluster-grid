"""Isolated PostgreSQL gate: no existing application tables are touched."""
import asyncio
import hashlib
import os
import uuid

import asyncpg
import pytest

from grid.historical_science_import import canonical_payload, import_historical_science
from grid.migrations import MIGRATIONS


@pytest.mark.skipif(not os.environ.get("POSTGRES_DSN"), reason="isolated PostgreSQL DSN required")
def test_import_rollback_and_concurrent_redelivery_postgres():
    async def scenario():
        schema = "science_atomic_" + uuid.uuid4().hex
        admin = await asyncpg.connect(os.environ["POSTGRES_DSN"])
        pool = None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')

            async def setup(conn):
                await conn.execute(f'SET search_path TO "{schema}"')

            pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"],
                                            min_size=2, max_size=4, setup=setup)
            for version, _, statements in MIGRATIONS:
                if version == 42:
                    for sql in statements:
                        await pool.execute(sql)
            await pool.execute("ALTER TABLE historical_scientific_symbol_state "
                               "ADD CONSTRAINT nonnegative_samples CHECK(samples >= 0)")
            value = {
                "schema": 1, "source": "strattester", "created_at": 1.0,
                "research_scope": "HISTORICAL_BOOTSTRAP_ONLY",
                "capabilities": {"candles": True, "open_interest": True,
                                 "public_trade_aggregates": True},
                "symbols": [{"symbol": "BTCUSDT", "samples": 2},
                            {"symbol": "ETHUSDT", "samples": -1}],
            }
            value["sha256"] = hashlib.sha256(canonical_payload(value).encode()).hexdigest()
            with pytest.raises(asyncpg.CheckViolationError):
                await import_historical_science(pool, value)
            assert await pool.fetchval("SELECT count(*) FROM historical_scientific_bundles") == 0
            assert await pool.fetchval("SELECT count(*) FROM historical_scientific_symbol_state") == 0

            value["symbols"][1]["samples"] = 3
            value["sha256"] = hashlib.sha256(canonical_payload(value).encode()).hexdigest()
            first, repeated = await asyncio.wait_for(asyncio.gather(
                import_historical_science(pool, value),
                import_historical_science(pool, value)), 10)
            assert first["bundle_id"] == repeated["bundle_id"]
            assert first["live_evidence_promoted"] is False
            assert await pool.fetchval("SELECT count(*) FROM historical_scientific_bundles") == 1
            assert await pool.fetchval("SELECT count(*) FROM historical_scientific_symbol_state") == 2
        finally:
            if pool is not None:
                await pool.close()
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    asyncio.run(scenario())
