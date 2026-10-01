import asyncio
from datetime import datetime, timedelta, timezone
import os
import time
import uuid

import asyncpg
import pytest

from grid.enrollment import create_enrollment_token, enroll, ensure_enrollment_schema
from grid.runtime_gate import ensure_runtime_gate, set_runtime_state
from grid.server_pilot import begin_server_pilot_validation


DSN = os.environ["POSTGRES_DSN"]


async def reset(pool):
    await pool.execute("DROP TABLE IF EXISTS fleet_operations")
    await pool.execute("DROP TABLE IF EXISTS enrollment_tokens")
    await pool.execute("DROP TABLE IF EXISTS agent_credentials")
    await pool.execute("DROP TABLE IF EXISTS pilot_bootstrap_state")
    await pool.execute("DROP TABLE IF EXISTS grid_runtime_state")
    await pool.execute(
        """
        CREATE TABLE pilot_bootstrap_state(
          node_id text PRIMARY KEY,
          mode text NOT NULL DEFAULT 'PILOT_BOOTSTRAP',
          phase text NOT NULL DEFAULT 'WAITING',
          paused boolean NOT NULL DEFAULT false,
          progress numeric NOT NULL DEFAULT 0,
          source_path text,
          research_path text,
          details jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          expansion_notified_at timestamptz
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE fleet_operations(
          id uuid PRIMARY KEY,
          action text NOT NULL,
          status text NOT NULL,
          requested_by text NOT NULL,
          snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          targets jsonb NOT NULL DEFAULT '[]'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          details jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    await ensure_enrollment_schema(pool)
    await ensure_runtime_gate(pool)
    await set_runtime_state(pool, "STOPPED", "test", "pilot validation test")


def future():
    return datetime.now(timezone.utc) + timedelta(minutes=15)


def node():
    return {
        "last_seen": time.time(),
        "integrity_ok": True,
        "operator_stopped": True,
        "wanted_symbols": 0,
        "active_trade_streams": 0,
    }


def test_postgres_clean_pilot_validation_transition_is_durable_and_gate_stays_stopped():
    async def scenario():
        pool = await asyncpg.create_pool(DSN)
        try:
            await reset(pool)
            nid = "pilot-" + uuid.uuid4().hex
            token = await create_enrollment_token(pool, "pilot", future(), "PILOT")
            await enroll(pool, token, nid)
            await pool.execute(
                "UPDATE pilot_bootstrap_state SET paused=true WHERE node_id=$1", nid
            )

            state = await begin_server_pilot_validation(
                pool, nid, {nid: node()}, heartbeat_seconds=10
            )
            assert state["mode"] == "PILOT_VALIDATING"
            assert state["phase"] == "LIVE_CANARY"
            assert state["paused"] is False
            assert float(state["progress"]) == 90.0

            gate = await pool.fetchval(
                "SELECT state FROM grid_runtime_state WHERE singleton=true"
            )
            assert gate == "STOPPED"

            # Re-open the pool to prove lifecycle persistence across process restart.
            await pool.close()
            pool2 = await asyncpg.create_pool(DSN)
            try:
                persisted = await pool2.fetchrow(
                    "SELECT mode,phase,paused,progress FROM pilot_bootstrap_state WHERE node_id=$1",
                    nid,
                )
                assert persisted["mode"] == "PILOT_VALIDATING"
                assert persisted["phase"] == "LIVE_CANARY"
                assert persisted["paused"] is False
                assert float(persisted["progress"]) == 90.0
                assert await pool2.fetchval(
                    "SELECT state FROM grid_runtime_state WHERE singleton=true"
                ) == "STOPPED"
            finally:
                await pool2.close()
            return
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_postgres_active_gate_blocks_lifecycle_mutation():
    async def scenario():
        pool = await asyncpg.create_pool(DSN)
        try:
            await reset(pool)
            nid = "pilot-" + uuid.uuid4().hex
            token = await create_enrollment_token(pool, "pilot", future(), "PILOT")
            await enroll(pool, token, nid)
            await set_runtime_state(pool, "ACTIVE", "test", "must block transition")

            with pytest.raises(ValueError, match="global runtime must be STOPPED"):
                await begin_server_pilot_validation(
                    pool, nid, {nid: node()}, heartbeat_seconds=10
                )

            state = await pool.fetchrow(
                "SELECT mode,phase FROM pilot_bootstrap_state WHERE node_id=$1", nid
            )
            assert state["mode"] == "PILOT_BOOTSTRAP"
            assert state["phase"] == "WAITING"
        finally:
            await pool.close()

    asyncio.run(scenario())
