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


async def unreferenced_content_candidates(pool,retention_days=30,limit=100):
    return await pool.fetch("""SELECT a.* FROM ml_artifacts a
      WHERE a.status='ACTIVE'
        AND a.storage_uri LIKE 'content://sha256/%'
        AND a.last_used_at<now()-($1::int*interval '1 day')
        AND NOT EXISTS(SELECT 1 FROM dataset_snapshots d WHERE d.artifact_id=a.id)
        AND NOT EXISTS(SELECT 1 FROM research_runs r
          WHERE r.result_artifact_id=a.id OR r.dataset_artifact_id=a.id)
        AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=a.id)
        AND NOT EXISTS(SELECT 1 FROM ml_artifacts other
          WHERE other.storage_uri=a.storage_uri AND other.status='ACTIVE' AND other.id<>a.id)
      ORDER BY a.last_used_at,a.created_at LIMIT $2""",int(retention_days),int(limit))


async def delete_unreferenced_content_artifacts(pool,cache,retention_days=30,limit=100):
    rows=await unreferenced_content_candidates(pool,retention_days,limit)
    deleted=0
    prefix="content://sha256/"
    for row in rows:
        changed=await pool.execute("""UPDATE ml_artifacts SET status='DELETING'
          WHERE id=$1 AND status='ACTIVE'
            AND NOT EXISTS(SELECT 1 FROM dataset_snapshots d WHERE d.artifact_id=ml_artifacts.id)
            AND NOT EXISTS(SELECT 1 FROM research_runs r
              WHERE r.result_artifact_id=ml_artifacts.id OR r.dataset_artifact_id=ml_artifacts.id)
            AND NOT EXISTS(SELECT 1 FROM model_registry m WHERE m.artifact_id=ml_artifacts.id)""",row["id"])
        if not changed.endswith(" 1"):continue
        uri=str(row["storage_uri"])
        active_same=await pool.fetchval("""SELECT count(*) FROM ml_artifacts
          WHERE storage_uri=$1 AND status='ACTIVE'""",uri)
        if not active_same and uri.startswith(prefix):
            try:cache.discard(uri[len(prefix):])
            except (ValueError,OSError):pass
        await pool.execute("UPDATE ml_artifacts SET status='DELETED' WHERE id=$1 AND status='DELETING'",row["id"])
        deleted+=1
    return deleted
