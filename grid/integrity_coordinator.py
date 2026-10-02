import logging
from .repair_health import begin_repair,note_repair_heartbeat
from .control_plane import enqueue_command

log=logging.getLogger("integrity_coordinator")

async def handle_integrity_heartbeat(pool,node_id,payload,breaker):
    ok=bool(payload.get("integrity_ok",True))
    version=str(payload.get("agent_version") or "")
    state=await note_repair_heartbeat(pool,node_id,version,ok)
    if ok:return {"repair_state":state}
    active=await pool.fetchval("""SELECT count(*) FROM integrity_repairs WHERE node_id=$1
      AND status IN ('queued','verifying','rollback_pending')""",node_id)
    if active:return {"repair_state":state or "active"}
    if not breaker.allow(node_id):return {"repair_state":"circuit_open"}
    files=payload.get("integrity_bad",[])+payload.get("integrity_missing",[])
    if not files:return {"repair_state":"invalid_report"}
    try:
        rid,repair=await begin_repair(pool,node_id,files,version,3)
    except RuntimeError as exc:
        # A missing repair target is a control-plane configuration problem, not
        # a reason to turn a valid authenticated heartbeat into HTTP 500.
        log.error("integrity repair unavailable node=%s version=%s error=%s",node_id,version,exc)
        return {"repair_state":"unavailable","repair_error":str(exc)[:200]}
    await enqueue_command(pool,node_id,"repair",repair)
    breaker.record(node_id)
    return {"repair_state":"queued","repair_id":str(rid)}
