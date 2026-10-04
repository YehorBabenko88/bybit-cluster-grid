import logging
log=logging.getLogger("operational_gc")


async def cleanup_operational_state(pool,terminal_days=30,batch_size=1000):
    deleted={}
    statements={
      "ml_resource_reservations":"""DELETE FROM ml_resource_reservations r WHERE r.job_id IN (
        SELECT id FROM ml_jobs WHERE status IN ('done','failed','cancelled')
        AND finished_at<now()-($1::int*interval '1 day'))""",
      "archive_compute_jobs":"""WITH d AS (SELECT id FROM archive_compute_jobs
        WHERE status IN ('done','failed') AND updated_at<now()-($1::int*interval '1 day')
        ORDER BY updated_at LIMIT $2) DELETE FROM archive_compute_jobs x USING d WHERE x.id=d.id""",
      "research_runs":"""WITH d AS (SELECT id FROM research_runs
        WHERE status IN ('COMPLETE','FAILED','CANCELLED') AND finished_at<now()-($1::int*interval '1 day')
        ORDER BY finished_at LIMIT $2) DELETE FROM research_runs x USING d WHERE x.id=d.id""",
      "ml_jobs":"""WITH d AS (SELECT id FROM ml_jobs
        WHERE status IN ('done','failed','cancelled') AND finished_at<now()-($1::int*interval '1 day')
        AND NOT EXISTS(SELECT 1 FROM research_shards s WHERE ('strattester:'||s.id::text)=ml_jobs.dedupe_key)
        ORDER BY finished_at LIMIT $2) DELETE FROM ml_jobs x USING d WHERE x.id=d.id""",
    }
    for name,sql in statements.items():
        try:
            args=(int(terminal_days),int(batch_size)) if "$2" in sql else (int(terminal_days),)
            r=await pool.execute(sql,*args);deleted[name]=int(r.split()[-1])
        except Exception:
            log.exception("operational gc failed",extra={"event":"operational_gc_failed","table":name})
            deleted[name]=0
    return deleted
