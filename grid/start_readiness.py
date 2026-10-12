"""Readiness gate for the first global START.

The runtime gate remains fail-closed until CONTROL can prove that there is at
least one enrolled, currently-online agent and no conflicting fleet lifecycle
operation.  The check is deliberately repeated at confirmation time to avoid
TOCTOU races between /begin and /confirm.
"""
import time

BLOCKING_OPERATION_STATUSES={
    "RUNNING","WAITING","READY_CONTROL_PURGE","CONTROL_PURGE_STARTED"
}

async def start_readiness(pool,nodes,heartbeat_seconds):
    missing=[]
    details={}

    # Database/control-plane liveness.
    try:
        await pool.fetchval("SELECT 1")
    except Exception:
        return {"ready":False,"missing":["database_unavailable"],"details":{}}

    try:
        registered_rows=await pool.fetch(
            "SELECT node_id FROM agent_credentials WHERE revoked_at IS NULL ORDER BY node_id"
        )
        registered=[r["node_id"] for r in registered_rows]
    except Exception:
        registered=[]
        missing.append("agent_registry_unavailable")

    details["registered_agents"]=registered
    if not registered:
        missing.append("no_registered_agents")

    now=time.time()
    online=[]
    unhealthy=[]
    for node_id in registered:
        node=nodes.get(node_id)
        if not node:
            continue
        if now-float(node.get("last_seen",0)) >= heartbeat_seconds*3:
            continue
        online.append(node_id)
        if node.get("integrity_ok") is False:
            unhealthy.append(node_id)

    details["online_agents"]=online
    details["unhealthy_agents"]=unhealthy
    if registered and not online:
        missing.append("no_online_registered_agents")
    if unhealthy:
        missing.append("agent_integrity_failed")

    try:
        op=await pool.fetchrow(
            """SELECT action,status FROM fleet_operations
               WHERE status = ANY($1::text[])
               ORDER BY created_at DESC LIMIT 1""",
            list(BLOCKING_OPERATION_STATUSES),
        )
    except Exception:
        op=None
        missing.append("fleet_operations_unavailable")
    if op:
        details["blocking_operation"]={"action":op["action"],"status":op["status"]}
        missing.append("fleet_operation_in_progress")

    # Keep output deterministic and compact for Telegram/tests.
    missing=list(dict.fromkeys(missing))
    return {"ready":not missing,"missing":missing,"details":details}
