"""Guarded CONTROL-owned transitions for a clean PILOT canary.

This path is intentionally independent from the legacy PilotBootstrap runner.
It never opens the global runtime gate and never promotes a pilot to NORMAL.
"""
from .enrollment import registered_install_mode
from .pilot_state import pilot_state, update_pilot
from .runtime_gate import runtime_state

_ALLOWED_FROM = {
    ("PILOT_BOOTSTRAP", "WAITING"),
    ("PILOT_VALIDATING", "LIVE_CANARY"),
}


async def begin_server_pilot_validation(pool, node_id, nodes, heartbeat_seconds):
    """Move an enrolled PILOT into LIVE_CANARY after strict fail-closed guards.

    The caller must explicitly open the global runtime gate separately.  This
    function only changes the pilot lifecycle row.
    """
    install_mode = await registered_install_mode(pool, node_id)
    if install_mode != "PILOT":
        raise ValueError(f"{node_id} is not server-authorized PILOT")

    gate = await runtime_state(pool)
    if gate["state"] != "STOPPED":
        raise ValueError(f"global runtime must be STOPPED, got {gate['state']}")

    state = await pilot_state(pool, node_id)
    if not state:
        raise ValueError("pilot lifecycle is missing")
    current = (state.get("mode"), state.get("phase"))
    if current not in _ALLOWED_FROM:
        raise ValueError(
            f"pilot lifecycle cannot enter validation from {current[0]}/{current[1]}"
        )

    node = nodes.get(node_id)
    if not node:
        raise ValueError("pilot node is not present in coordinator heartbeat state")

    import time
    age = max(0.0, time.time() - float(node.get("last_seen", 0) or 0))
    if age >= float(heartbeat_seconds) * 3:
        raise ValueError("pilot node is offline")
    if node.get("integrity_ok") is not True:
        raise ValueError("pilot node integrity is not healthy")
    if not bool(node.get("operator_stopped", False)):
        raise ValueError("pilot node must remain operator-stopped before validation")
    if int(node.get("wanted_symbols", 0) or 0) != 0:
        raise ValueError("pilot node already has wanted symbols")
    if int(node.get("active_trade_streams", 0) or 0) != 0:
        raise ValueError("pilot node already has active trade streams")

    blocking = await pool.fetchrow(
        """SELECT action,status FROM fleet_operations
           WHERE status IN ('RUNNING','WAITING','READY_CONTROL_PURGE','CONTROL_PURGE_STARTED')
           ORDER BY created_at DESC LIMIT 1"""
    )
    if blocking:
        raise ValueError(
            f"fleet operation blocks pilot validation: {blocking['action']}/{blocking['status']}"
        )

    details = dict(state.get("details") or {})
    details.update({
        "server_controlled_validation": True,
        "legacy_runner": False,
        "validation_requested": True,
    })
    await update_pilot(
        pool,
        node_id,
        mode="PILOT_VALIDATING",
        phase="LIVE_CANARY",
        progress=max(float(state.get("progress") or 0), 90.0),
        paused=False,
        details=details,
    )
    return await pilot_state(pool, node_id)
