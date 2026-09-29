import json

MODES={"PILOT_BOOTSTRAP","PILOT_VALIDATING","READY_FOR_EXPANSION","NORMAL","PAUSED"}
PHASES={"WAITING","INVENTORY","REPAIR_HISTORY","LEVEL_RESEARCH","IMPORT","VERIFY","LIVE_CANARY","COMPLETE","FAILED"}

async def ensure_pilot(pool,node_id,source_path=None,research_path=None):
    await pool.execute("""INSERT INTO pilot_bootstrap_state(node_id,source_path,research_path)
      VALUES($1,$2,$3) ON CONFLICT(node_id) DO UPDATE SET
      source_path=COALESCE(EXCLUDED.source_path,pilot_bootstrap_state.source_path),
      research_path=COALESCE(EXCLUDED.research_path,pilot_bootstrap_state.research_path),
      updated_at=now()""",node_id,source_path,research_path)

async def update_pilot(pool,node_id,mode=None,phase=None,progress=None,paused=None,details=None):
    if mode is not None and mode not in MODES:raise ValueError("invalid pilot mode")
    if phase is not None and phase not in PHASES:raise ValueError("invalid pilot phase")
    await ensure_pilot(pool,node_id)
    await pool.execute("""UPDATE pilot_bootstrap_state SET
      mode=COALESCE($2,mode),phase=COALESCE($3,phase),progress=COALESCE($4,progress),
      paused=COALESCE($5,paused),details=details||$6::jsonb,updated_at=now(),
      completed_at=CASE WHEN $3='COMPLETE' THEN now() ELSE completed_at END
      WHERE node_id=$1""",node_id,mode,phase,progress,paused,json.dumps(details or {}))

async def pilot_state(pool,node_id=None):
    if node_id:
        r=await pool.fetchrow("SELECT * FROM pilot_bootstrap_state WHERE node_id=$1",node_id)
        return dict(r) if r else None
    return [dict(r) for r in await pool.fetch("SELECT * FROM pilot_bootstrap_state ORDER BY node_id")]

async def node_live_mode(pool,node_id):
    """Return the explicitly persisted live mode for a node.

    Missing or invalid pilot state is fail-closed. A newly enrolled or
    incompletely initialized node must never inherit NORMAL live-market
    permissions merely because its pilot state is absent or malformed.
    """
    r=await pool.fetchrow(
        "SELECT mode,paused FROM pilot_bootstrap_state WHERE node_id=$1",
        node_id,
    )
    if not r:
        return "PAUSED"
    if r["paused"]:
        return "PAUSED"

    mode=r["mode"]
    if mode not in MODES:
        return "PAUSED"
    return mode

async def node_accepts_live_assignments(pool,node_id):
    return (await node_live_mode(pool,node_id))=="NORMAL"

async def expansion_ready(pool):
    rows=await pool.fetch("""SELECT * FROM pilot_bootstrap_state
      WHERE mode='READY_FOR_EXPANSION' AND phase='COMPLETE' AND paused=false""")
    return [dict(r) for r in rows]

async def mark_expansion_notified(pool,node_id):
    await pool.execute("""UPDATE pilot_bootstrap_state SET expansion_notified_at=now(),updated_at=now()
      WHERE node_id=$1 AND expansion_notified_at IS NULL""",node_id)
