import asyncio,logging
log=logging.getLogger("retention_v2")

TABLE_TS={"market_events":"event_ts","orderbook_snapshots":"ts","footprint_1m":"ts",
          "candles_1m":"ts","derivatives_metrics":"ts"}

async def register_consumer(pool,dataset,consumer,required=True,active=True):
    await pool.execute("""INSERT INTO retention_consumers(dataset,consumer,required,active)
      VALUES($1,$2,$3,$4)
      ON CONFLICT(dataset,consumer) DO UPDATE SET required=EXCLUDED.required,
      active=EXCLUDED.active,updated_at=now()""",dataset,consumer,bool(required),bool(active))

async def cleanup_dataset_safe(pool,dataset,retention_days,batch_size=10000,max_batches=20):
    if dataset not in TABLE_TS:raise ValueError("unsupported dataset")
    if int(retention_days)<0 or int(batch_size)<1 or int(max_batches)<1:
        raise ValueError("retention_days must be nonnegative; batch_size and max_batches positive")
    ts=TABLE_TS[dataset]; deleted=0
    sql=f"""WITH safe AS (
      SELECT t.symbol,min(cw.consumed_through) AS safe_through
      FROM {dataset} t
      CROSS JOIN retention_consumers rc
      LEFT JOIN consumer_watermarks cw
        ON cw.dataset=rc.dataset AND cw.consumer=rc.consumer AND cw.symbol=t.symbol
      WHERE rc.dataset=$3 AND rc.required=true AND rc.active=true
      GROUP BY t.symbol
      HAVING count(cw.consumer)=count(*) AND bool_and(cw.consumed_through IS NOT NULL)
    ), doomed AS (
      SELECT t.ctid FROM {dataset} t
      JOIN safe w ON w.symbol=t.symbol
      WHERE t.{ts}<now()-($1::int*interval '1 day') AND t.{ts}<=w.safe_through
      AND NOT EXISTS (
        SELECT 1 FROM retention_holds h WHERE h.dataset=$3
        AND (h.symbol IS NULL OR h.symbol=t.symbol)
        AND (h.expires_at IS NULL OR h.expires_at>now())
        AND (h.from_ts IS NULL OR t.{ts}>=h.from_ts)
        AND (h.through_ts IS NULL OR t.{ts}<=h.through_ts)
      )
      LIMIT $2
    ) DELETE FROM {dataset} t USING doomed d WHERE t.ctid=d.ctid"""
    async with pool.acquire() as c:
        # Stabilize required-consumer membership, watermarks, and retention holds
        # for each delete batch; concurrent writers acquire conflicting locks.
        for _ in range(int(max_batches)):
            async with c.transaction():
                await c.execute(
                    "LOCK TABLE retention_consumers, consumer_watermarks, retention_holds IN SHARE MODE"
                )
                required = await c.fetchval(
                    "SELECT count(*) FROM retention_consumers "
                    "WHERE dataset=$1 AND required=true AND active=true", dataset
                )
                if not required:
                    log.info("retention blocked: no required consumers registered",
                             extra={"event":"retention_blocked","dataset":dataset})
                    break
                r=await c.execute(sql,int(retention_days),int(batch_size),dataset)
            n=int(r.split()[-1]);deleted+=n
            if n<int(batch_size):break
            await asyncio.sleep(.05)
    return deleted


async def retention_backlog(pool,dataset,retention_days):
    """Planner estimate of rows past policy age; avoids a periodic full COUNT scan."""
    if dataset not in TABLE_TS:raise ValueError("unsupported dataset")
    ts=TABLE_TS[dataset]
    plan=await pool.fetchval(
        f"EXPLAIN (FORMAT JSON) SELECT 1 FROM {dataset} WHERE {ts}<now()-($1::int*interval '1 day')",
        int(retention_days))
    if isinstance(plan,str):
        import json
        plan=json.loads(plan)
    try:return max(0,int(plan[0]["Plan"]["Plan Rows"]))
    except (TypeError,KeyError,IndexError,ValueError):return 0
