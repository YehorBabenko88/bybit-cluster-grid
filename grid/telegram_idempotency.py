async def claim_update(pool,update_id,chat_id,command,node_id):
    r=await pool.execute("""INSERT INTO telegram_updates(update_id,chat_id,command,claimed_by)
      VALUES($1,$2,$3,$4) ON CONFLICT(update_id) DO NOTHING""",
      int(update_id),str(chat_id) if chat_id is not None else None,command,node_id)
    return r.endswith(" 1")

async def complete_update(pool,update_id,error=None):
    await pool.execute("""UPDATE telegram_updates SET status=$2,completed_at=now(),error=$3
      WHERE update_id=$1""",int(update_id),"FAILED" if error else "DONE",error)
