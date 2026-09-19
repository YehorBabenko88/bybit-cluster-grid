"""Persistent fail-closed fleet runtime gate.

Infrastructure/control/update traffic is always allowed. Market acquisition, archive
backfill, strategy jobs and learning are allowed only while state == ACTIVE.
"""
VALID_STATES={"INFRA_ONLY","START_REQUESTED","ACTIVE","PAUSED"}

async def ensure_runtime_gate(pool):
    await pool.execute("""CREATE TABLE IF NOT EXISTS grid_runtime_state(
      singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
      state text NOT NULL DEFAULT 'INFRA_ONLY',
      requested_by text,
      reason text,
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK(state IN ('INFRA_ONLY','START_REQUESTED','ACTIVE','PAUSED'))
    )""")
    await pool.execute("""INSERT INTO grid_runtime_state(singleton,state,reason)
      VALUES(true,'INFRA_ONLY','safe default')
      ON CONFLICT(singleton) DO NOTHING""")

async def runtime_state(pool):
    try:
        row=await pool.fetchrow("SELECT state,requested_by,reason,updated_at FROM grid_runtime_state WHERE singleton=true")
    except Exception:
        return {"state":"INFRA_ONLY","requested_by":None,"reason":"gate unavailable","updated_at":None}
    return dict(row) if row else {"state":"INFRA_ONLY","requested_by":None,"reason":"gate missing","updated_at":None}

async def market_work_allowed(pool):
    return (await runtime_state(pool))["state"]=="ACTIVE"

async def set_runtime_state(pool,state,requested_by,reason=None):
    state=str(state).upper()
    if state not in VALID_STATES:
        raise ValueError("invalid runtime state")
    await ensure_runtime_gate(pool)
    await pool.execute("""UPDATE grid_runtime_state
      SET state=$1,requested_by=$2,reason=$3,updated_at=now()
      WHERE singleton=true""",state,str(requested_by),reason)
    return await runtime_state(pool)
