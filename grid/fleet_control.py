"""Durable fleet-wide lifecycle operations.

Global state always dominates node-local intent.  STOP snapshots the pre-stop
node state so RESUME never wakes a node that the operator had already stopped.
DELETE is fail-closed: CONTROL must remain alive until every target agent has
accepted its purge command.
"""
import json, uuid
from .control_plane import enqueue_command
from .runtime_gate import set_runtime_state, runtime_state

async def ensure_fleet_schema(pool):
    await pool.execute("""CREATE TABLE IF NOT EXISTS fleet_operations(
      id uuid PRIMARY KEY, action text NOT NULL, status text NOT NULL,
      requested_by text NOT NULL, snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
      targets jsonb NOT NULL DEFAULT '[]'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
      details jsonb NOT NULL DEFAULT '{}'::jsonb)""")
    await pool.execute("""CREATE INDEX IF NOT EXISTS fleet_operations_status_idx
      ON fleet_operations(action,status,created_at DESC)""")

async def latest_operation(pool, action=None):
    await ensure_fleet_schema(pool)
    if action:
        row=await pool.fetchrow("SELECT * FROM fleet_operations WHERE action=$1 ORDER BY created_at DESC LIMIT 1",action)
    else:
        row=await pool.fetchrow("SELECT * FROM fleet_operations ORDER BY created_at DESC LIMIT 1")
    return dict(row) if row else None

async def fleet_stop(pool,nodes,requested_by):
    await ensure_fleet_schema(pool)
    current=await runtime_state(pool)
    if current["state"]=="PAUSED":
        return {"state":"PAUSED","commands":[],"already":True}
    snapshot={}
    targets=[]
    for nid,n in sorted(nodes.items()):
        # Preserve nodes that were already locally stopped/paused.
        snapshot[nid]={
          "operator_stopped":bool(n.get("operator_stopped",False)),
          "bootstrap_paused":bool(n.get("bootstrap_paused",False)),
        }
        targets.append(nid)
    op=uuid.uuid4()
    await pool.execute("""INSERT INTO fleet_operations(id,action,status,requested_by,snapshot,targets)
      VALUES($1,'STOP','RUNNING',$2,$3::jsonb,$4::jsonb)""",op,str(requested_by),json.dumps(snapshot),json.dumps(targets))
    # Gate first: no heartbeat race can re-enable market work while commands fan out.
    await set_runtime_state(pool,"PAUSED",requested_by,"global STOP")
    commands=[]
    for nid in targets:
        commands.append((nid,await enqueue_command(pool,nid,"stop",{"scope":"fleet","operation_id":str(op)})))
    await pool.execute("UPDATE fleet_operations SET status='DONE',completed_at=now() WHERE id=$1",op)
    return {"state":"PAUSED","operation_id":str(op),"commands":commands}

async def fleet_resume(pool,nodes,requested_by):
    await ensure_fleet_schema(pool)
    prev=await latest_operation(pool,"STOP")
    snapshot=(prev or {}).get("snapshot") or {}
    op=uuid.uuid4(); targets=sorted(nodes)
    await pool.execute("""INSERT INTO fleet_operations(id,action,status,requested_by,snapshot,targets)
      VALUES($1,'RESUME','RUNNING',$2,$3::jsonb,$4::jsonb)""",op,str(requested_by),json.dumps(snapshot),json.dumps(targets))
    commands=[]
    # Restore local intent before opening the global gate. Already-stopped nodes stay stopped.
    for nid in targets:
        before=snapshot.get(nid,{})
        if before.get("operator_stopped"):
            continue
        action="pause" if before.get("bootstrap_paused") else "start"
        commands.append((nid,await enqueue_command(pool,nid,action,{"scope":"fleet","operation_id":str(op)})))
    await set_runtime_state(pool,"ACTIVE",requested_by,"global RESUME")
    await pool.execute("UPDATE fleet_operations SET status='DONE',completed_at=now() WHERE id=$1",op)
    return {"state":"ACTIVE","operation_id":str(op),"commands":commands,"preserved_stopped":[n for n,v in snapshot.items() if v.get("operator_stopped")]}

async def begin_fleet_delete(pool,nodes,requested_by):
    await ensure_fleet_schema(pool)
    existing=await latest_operation(pool,"DELETE")
    if existing and existing["status"] in ("WAITING","READY_CONTROL_PURGE"):
        return {"operation_id":str(existing["id"]),"targets":existing["targets"],"existing":True}
    targets=sorted(nodes)
    op=uuid.uuid4()
    await set_runtime_state(pool,"PAUSED",requested_by,"global DELETE pending")
    await pool.execute("""INSERT INTO fleet_operations(id,action,status,requested_by,targets)
      VALUES($1,'DELETE','WAITING',$2,$3::jsonb)""",op,str(requested_by),json.dumps(targets))
    commands=[]
    for nid in targets:
        commands.append((nid,await enqueue_command(pool,nid,"uninstall",{"purge_data":True,"scope":"fleet-delete","operation_id":str(op)})))
    return {"operation_id":str(op),"targets":targets,"commands":commands}

async def fleet_delete_status(pool,operation_id):
    await ensure_fleet_schema(pool)
    op=await pool.fetchrow("SELECT * FROM fleet_operations WHERE id=$1::uuid",operation_id)
    if not op: return None
    targets=list(op["targets"] or [])
    rows=await pool.fetch("""SELECT node_id,status,error FROM agent_commands
      WHERE action='uninstall' AND payload->>'operation_id'=$1""",str(operation_id))
    by={r["node_id"]:dict(r) for r in rows}
    pending=[n for n in targets if by.get(n,{}).get("status")!="done"]
    failed={n:by[n].get("error") for n in targets if by.get(n,{}).get("status")=="failed"}
    status="READY_CONTROL_PURGE" if not pending and not failed else "WAITING"
    await pool.execute("UPDATE fleet_operations SET status=$2,details=$3::jsonb WHERE id=$1::uuid",
                       str(operation_id),status,json.dumps({"pending":pending,"failed":failed}))
    return {"status":status,"pending":pending,"failed":failed,"targets":targets}
