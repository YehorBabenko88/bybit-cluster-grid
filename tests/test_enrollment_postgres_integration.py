import asyncio
from datetime import datetime, timedelta, timezone
import os
import uuid

import asyncpg
import pytest

from grid.enrollment import (
    authenticate_agent,
    create_enrollment_token,
    enroll,
    ensure_enrollment_schema,
    registered_install_mode,
)


DSN = os.environ["POSTGRES_DSN"]


async def _reset(pool):
    await pool.execute("DROP TABLE IF EXISTS enrollment_tokens")
    await pool.execute("DROP TABLE IF EXISTS agent_credentials")
    await pool.execute("DROP TABLE IF EXISTS pilot_bootstrap_state")
    await pool.execute(
        """
        CREATE TABLE pilot_bootstrap_state(
          node_id text PRIMARY KEY,
          mode text NOT NULL DEFAULT 'PILOT_BOOTSTRAP',
          phase text NOT NULL DEFAULT 'WAITING',
          paused boolean NOT NULL DEFAULT false,
          progress integer NOT NULL DEFAULT 0,
          source_path text,
          research_path text,
          details jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          expansion_notified_at timestamptz
        )
        """
    )
    await ensure_enrollment_schema(pool)


def _future():
    return datetime.now(timezone.utc) + timedelta(minutes=15)


def test_fresh_pilot_enrollment_is_server_authorized_and_persistent():
    async def scenario():
        pool = await asyncpg.create_pool(DSN)
        try:
            await _reset(pool)
            node = "pilot-" + uuid.uuid4().hex
            token = await create_enrollment_token(pool, "pilot", _future(), "PILOT")
            credential = await enroll(pool, token, node)

            assert await registered_install_mode(pool, node) == "PILOT"
            assert await authenticate_agent(pool, node, credential)
            state = await pool.fetchrow(
                "SELECT mode,phase,paused,progress FROM pilot_bootstrap_state WHERE node_id=$1",
                node,
            )
            assert dict(state) == {
                "mode": "PILOT_BOOTSTRAP",
                "phase": "WAITING",
                "paused": False,
                "progress": 0,
            }
        finally:
            await pool.close()

        # Simulate coordinator/process restart with a new connection pool.
        pool = await asyncpg.create_pool(DSN)
        try:
            assert await registered_install_mode(pool, node) == "PILOT"
            assert await authenticate_agent(pool, node, credential)
        finally:
            await pool.close()
    asyncio.run(scenario())


def test_token_is_one_use():
    async def scenario():
        pool = await asyncpg.create_pool(DSN)
        try:
            await _reset(pool)
            token = await create_enrollment_token(pool, "pilot", _future(), "PILOT")
            await enroll(pool, token, "pilot-a")
            with pytest.raises(ValueError, match="invalid/expired"):
                await enroll(pool, token, "pilot-b")
        finally:
            await pool.close()
    asyncio.run(scenario())


def test_normal_is_locked_until_pilot_ready():
    async def scenario():
        pool = await asyncpg.create_pool(DSN)
        try:
            await _reset(pool)
            with pytest.raises(ValueError, match="READY_FOR_EXPANSION"):
                await create_enrollment_token(pool, "normal", _future(), "NORMAL")

            pilot_token = await create_enrollment_token(pool, "pilot", _future(), "PILOT")
            await enroll(pool, pilot_token, "pilot")
            await pool.execute(
                """UPDATE pilot_bootstrap_state
                   SET mode='READY_FOR_EXPANSION',phase='COMPLETE',paused=false
                   WHERE node_id='pilot'"""
            )
            normal_token = await create_enrollment_token(pool, "normal", _future(), "NORMAL")
            await enroll(pool, normal_token, "agent")
            assert await registered_install_mode(pool, "agent") == "NORMAL"
        finally:
            await pool.close()
    asyncio.run(scenario())


def test_role_change_is_rejected_without_consuming_token():
    async def scenario():
        pool = await asyncpg.create_pool(DSN)
        try:
            await _reset(pool)
            pilot_token = await create_enrollment_token(pool, "pilot", _future(), "PILOT")
            await enroll(pool, pilot_token, "same-node")
            await pool.execute(
                """UPDATE pilot_bootstrap_state
                   SET mode='READY_FOR_EXPANSION',phase='COMPLETE',paused=false
                   WHERE node_id='same-node'"""
            )
            normal_token = await create_enrollment_token(pool, "normal", _future(), "NORMAL")
            with pytest.raises(ValueError, match="role does not match"):
                await enroll(pool, normal_token, "same-node")

            # A rejected role-change must roll back and leave the one-use token valid.
            await enroll(pool, normal_token, "different-node")
            assert await registered_install_mode(pool, "same-node") == "PILOT"
            assert await registered_install_mode(pool, "different-node") == "NORMAL"
        finally:
            await pool.close()
    asyncio.run(scenario())


def test_same_role_reenrollment_preserves_lifecycle_and_rotates_credential():
    async def scenario():
        pool = await asyncpg.create_pool(DSN)
        try:
            await _reset(pool)
            node = "pilot"
            first_token = await create_enrollment_token(pool, "first", _future(), "PILOT")
            first_credential = await enroll(pool, first_token, node)
            await pool.execute(
                """UPDATE pilot_bootstrap_state
                   SET mode='PILOT_VALIDATING',phase='LIVE_CANARY',progress=73
                   WHERE node_id=$1""",
                node,
            )

            retry_token = await create_enrollment_token(pool, "retry", _future(), "PILOT")
            second_credential = await enroll(pool, retry_token, node)
            state = await pool.fetchrow(
                "SELECT mode,phase,progress FROM pilot_bootstrap_state WHERE node_id=$1",
                node,
            )
            assert dict(state) == {
                "mode": "PILOT_VALIDATING",
                "phase": "LIVE_CANARY",
                "progress": 73,
            }
            assert not await authenticate_agent(pool, node, first_credential)
            assert await authenticate_agent(pool, node, second_credential)
        finally:
            await pool.close()
    asyncio.run(scenario())
