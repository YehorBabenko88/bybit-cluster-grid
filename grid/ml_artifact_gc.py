async def gc_candidates(pool,limit=200):
    return await pool.fetch("""SELECT a.* FROM ml_artifacts a
      WHERE a.status='ACTIVE' AND a.reusable=false AND a.expires_at IS NOT NULL AND a.expires_at<now()
      AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=a.id)
      ORDER BY a.expires_at ASC LIMIT $1""",int(limit))

async def mark_deleting(pool,artifact_id):
    r=await pool.execute("""UPDATE ml_artifacts a SET status='DELETING'
      WHERE a.id=$1 AND a.status='ACTIVE' AND a.reusable=false AND a.expires_at<now()
      AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=a.id)""",artifact_id)
    return r.endswith(" 1")

async def mark_deleted(pool,artifact_id):
    await pool.execute("UPDATE ml_artifacts SET status='DELETED' WHERE id=$1 AND status='DELETING'",artifact_id)

async def touch_artifact(pool,artifact_id):
    await pool.execute("UPDATE ml_artifacts SET last_used_at=now() WHERE id=$1 AND status='ACTIVE'",artifact_id)

async def delete_owned_artifacts(pool,store,limit=200):
    """Two-phase, retry-safe physical GC for local artifacts only."""
    rows=await pool.fetch("""SELECT a.* FROM ml_artifacts a
      WHERE a.status='DELETING'
      AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=a.id)
      ORDER BY a.expires_at NULLS FIRST,a.created_at LIMIT $1""",int(limit))
    deleted=skipped=0
    for row in rows:
        uri=row["storage_uri"]
        if not str(uri).startswith(store.scheme):
            skipped+=1;continue
        store.delete_uri(uri)
        await mark_deleted(pool,row["id"])
        deleted+=1
    return {"deleted":deleted,"skipped":skipped}
