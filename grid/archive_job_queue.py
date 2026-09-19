async def claim_archive_job(pool,max_attempts=5):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM trade_archive_backfill
              WHERE status IN ('queued','retry') AND attempts<$1
              ORDER BY archive_date,symbol FOR UPDATE SKIP LOCKED LIMIT 1""",int(max_attempts))
            if not row:return None
            await c.execute("""UPDATE trade_archive_backfill SET status='running',
              attempts=attempts+1,updated_at=now(),last_error=NULL
              WHERE symbol=$1 AND archive_date=$2""",row["symbol"],row["archive_date"])
            return dict(row)

async def fail_archive_job(pool,job,error,max_attempts=5):
    await pool.execute("""UPDATE trade_archive_backfill SET
      status=CASE WHEN attempts<$3 THEN 'retry' ELSE 'failed' END,
      last_error=$4,updated_at=now() WHERE symbol=$1 AND archive_date=$2""",
      job["symbol"],job["archive_date"],int(max_attempts),str(error)[:4000])

async def recover_stale_archive_jobs(pool,stale_minutes=30,max_attempts=5):
    return await pool.execute("""UPDATE trade_archive_backfill SET
      status=CASE WHEN attempts<$2 THEN 'retry' ELSE 'failed' END,
      last_error=COALESCE(last_error,'recovered stale archive worker'),updated_at=now()
      WHERE status='running' AND updated_at<now()-($1*interval '1 minute')""",
      int(stale_minutes),int(max_attempts))
