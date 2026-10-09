"""Real PostgreSQL concurrency and rollback checks for scientific simulation leases."""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest

from grid.scientific_simulation_gate import ScientificSimulationGate

DSN = os.environ.get("POSTGRES_DSN")


@pytest.mark.skipif(not DSN, reason="POSTGRES_DSN not configured")
def test_scientific_atomic_claim_and_expired_recovery():
    async def scenario():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=5)
        run_id = uuid.uuid4()
        hypothesis_id = uuid.uuid4()
        try:
            # Temporary tables are session-scoped; use a dedicated schema instead
            # to allow independent pooled connections to race safely.
            schema = "science_ci_" + uuid.uuid4().hex[:16]
            async with pool.acquire() as conn:
                await conn.execute(f'CREATE SCHEMA "{schema}"')
            try:
                async with pool.acquire() as conn:
                    await conn.execute(f'SET search_path TO "{schema}",public')
                    await conn.execute("""CREATE TABLE scientific_simulation_runs(
                        id uuid PRIMARY KEY, hypothesis_id uuid NOT NULL,
                        dataset_cutoff timestamptz NOT NULL, status text NOT NULL DEFAULT 'QUEUED',
                        created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz,
                        attempts integer NOT NULL DEFAULT 0, lease_token uuid,
                        lease_expires_at timestamptz, reason text)""")
                    await conn.execute("""INSERT INTO scientific_simulation_runs
                        (id,hypothesis_id,dataset_cutoff) VALUES($1,$2,$3)""",
                        run_id,hypothesis_id,datetime.now(timezone.utc))
                # New pool connections each receive the dedicated test schema.
                await pool.close()
                pool2 = await asyncpg.create_pool(
                    DSN, min_size=2, max_size=5,
                    init=lambda conn: conn.execute(f'SET search_path TO "{schema}",public'))
                try:
                    class Gate(ScientificSimulationGate):
                        async def run_one(self,run_id,hypothesis_id,dataset_cutoff,
                                          claimed=False,lease_token=None):
                            assert claimed and lease_token
                            await asyncio.sleep(0.03)
                            return {"run_id":str(run_id),"status":"CLAIMED"}
                    first,second=await asyncio.gather(
                        Gate(pool2).run_queued(limit=1),
                        Gate(pool2).run_queued(limit=1))
                    assert sorted(map(len,(first,second)))==[0,1]
                    row=await pool2.fetchrow(
                        "SELECT attempts,status,lease_token FROM scientific_simulation_runs WHERE id=$1",
                        run_id)
                    assert row["attempts"]==1 and row["status"]=="RUNNING"
                    assert row["lease_token"] is not None
                    await pool2.execute("""UPDATE scientific_simulation_runs
                        SET lease_expires_at=now()-interval '1 minute' WHERE id=$1""",run_id)
                    await Gate(pool2).run_queued(limit=0)
                    row=await pool2.fetchrow(
                        "SELECT status,lease_token FROM scientific_simulation_runs WHERE id=$1",
                        run_id)
                    assert row["status"]=="QUEUED" and row["lease_token"] is None
                finally:
                    await pool2.close()
            finally:
                cleanup=await asyncpg.connect(DSN)
                try: await cleanup.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                finally: await cleanup.close()
        finally:
            if not pool._closed:
                await pool.close()
    asyncio.run(scenario())
