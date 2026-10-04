from __future__ import annotations
from datetime import datetime,timezone,timedelta


async def record_node_seen(pool,node_id,seen_at=None):
    seen_at=seen_at or datetime.now(timezone.utc)
    row=await pool.fetchrow("SELECT state FROM node_lifecycle WHERE node_id=$1",node_id)
    if row and row["state"]=="DECOMMISSIONED":
        return "DECOMMISSIONED"
    await pool.execute("""INSERT INTO node_lifecycle(node_id,state,last_seen,last_transition_at,updated_at)
      VALUES($1,'ONLINE',$2,now(),now())
      ON CONFLICT(node_id) DO UPDATE SET state='ONLINE',last_seen=EXCLUDED.last_seen,
      last_transition_at=CASE WHEN node_lifecycle.state<>'ONLINE' THEN now() ELSE node_lifecycle.last_transition_at END,
      quarantined_at=NULL,reason=NULL,updated_at=now()
      WHERE node_lifecycle.state<>'DECOMMISSIONED'""",node_id,seen_at)
    return "ONLINE"


async def reconcile_node_lifecycle(pool,offline_seconds=90,quarantine_hours=24,decommission_days=30):
    # Transitions are deliberately time-based and reversible until explicit long-term decommission.
    offline=await pool.execute("""UPDATE node_lifecycle SET state='OFFLINE',last_transition_at=now(),
      reason='heartbeat timeout',updated_at=now()
      WHERE state='ONLINE' AND last_seen<now()-($1::int*interval '1 second')""",int(offline_seconds))
    quarantine=await pool.execute("""UPDATE node_lifecycle SET state='QUARANTINED',quarantined_at=now(),
      last_transition_at=now(),reason='extended offline period',updated_at=now()
      WHERE state='OFFLINE' AND last_seen<now()-($1::int*interval '1 hour')""",int(quarantine_hours))
    decommission=await pool.execute("""UPDATE node_lifecycle SET state='DECOMMISSIONED',decommissioned_at=now(),
      last_transition_at=now(),reason='long-term offline; manual re-enrollment required',updated_at=now()
      WHERE state='QUARANTINED' AND last_seen<now()-($1::int*interval '1 day')""",int(decommission_days))
    # OFFLINE nodes also lose leases promptly. Their unfinished jobs are recovered by the normal
    # lease/retry reconciler; a returning node may claim fresh work after a heartbeat.
    blocked="('OFFLINE','QUARANTINED','DECOMMISSIONED')"
    # Any active compute lease owned by an unavailable node is made immediately reclaimable.
    await pool.execute("""UPDATE ml_jobs SET lease_until=now()
      WHERE status IN ('assigned','running') AND assigned_node IN
      (SELECT node_id FROM node_lifecycle WHERE state IN ('OFFLINE','QUARANTINED','DECOMMISSIONED'))""")
    await pool.execute("""UPDATE archive_compute_jobs SET lease_until=now()
      WHERE status='running' AND lease_owner IN
      (SELECT node_id FROM node_lifecycle WHERE state IN ('OFFLINE','QUARANTINED','DECOMMISSIONED'))""")
    return {"offline":offline,"quarantine":quarantine,"decommission":decommission}


async def node_may_compute(pool,node_id):
    state=await pool.fetchval("SELECT state FROM node_lifecycle WHERE node_id=$1",node_id)
    return state in (None,"ONLINE")
