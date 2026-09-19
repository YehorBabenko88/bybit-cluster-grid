import json,uuid
from .repair_protocol import stable_repair_request

async def begin_repair(pool,node_id,files,current_version=None,required_acks=3):
    payload=await stable_repair_request(pool,node_id,files,current_version)
    rid=uuid.uuid4()
    await pool.execute("""INSERT INTO integrity_repairs
      (id,node_id,target_version,required_health_acks,previous_version,files,status)
      VALUES($1,$2,$3,$4,$5,$6::jsonb,'queued')""",rid,node_id,payload["version"],
      int(required_acks),current_version,json.dumps(files))
    payload["repair_id"]=str(rid)
    return rid,payload

async def note_repair_heartbeat(pool,node_id,version,integrity_ok):
    row=await pool.fetchrow("""SELECT * FROM integrity_repairs WHERE node_id=$1
      AND status IN ('queued','verifying') ORDER BY created_at DESC LIMIT 1""",node_id)
    if not row:return None
    if row["deadline"] < await pool.fetchval("SELECT now()"):
        await pool.execute("UPDATE integrity_repairs SET status='rollback_pending',last_error='repair health timeout' WHERE id=$1",row["id"])
        return "rollback_pending"
    if version!=row["target_version"] or not integrity_ok:return "verifying"
    await pool.execute("""UPDATE integrity_repairs SET status='verifying',health_acks=health_acks+1
      WHERE id=$1""",row["id"])
    acks=await pool.fetchval("SELECT health_acks FROM integrity_repairs WHERE id=$1",row["id"])
    if acks>=row["required_health_acks"]:
        await pool.execute("UPDATE integrity_repairs SET status='healthy' WHERE id=$1",row["id"])
        return "healthy"
    return "verifying"

async def expired_repairs(pool):
    rows=await pool.fetch("""UPDATE integrity_repairs SET status='rollback_pending',
      last_error=COALESCE(last_error,'repair health timeout')
      WHERE status IN ('queued','verifying') AND deadline<now()
      RETURNING id,node_id,previous_version""")
    return [dict(r) for r in rows]
