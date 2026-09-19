async def gc_candidates(pool,limit=200):
    return await pool.fetch("""SELECT * FROM ml_artifacts
      WHERE status='ACTIVE' AND reusable=false AND expires_at IS NOT NULL AND expires_at<now()
      ORDER BY expires_at ASC LIMIT $1""",int(limit))

async def mark_deleting(pool,artifact_id):
    r=await pool.execute("""UPDATE ml_artifacts SET status='DELETING'
      WHERE id=$1 AND status='ACTIVE' AND reusable=false AND expires_at<now()""",artifact_id)
    return r.endswith(" 1")

async def mark_deleted(pool,artifact_id):
    await pool.execute("UPDATE ml_artifacts SET status='DELETED' WHERE id=$1 AND status='DELETING'",artifact_id)

async def touch_artifact(pool,artifact_id):
    await pool.execute("UPDATE ml_artifacts SET last_used_at=now() WHERE id=$1 AND status='ACTIVE'",artifact_id)
