import asyncio,logging
log=logging.getLogger("retention_v2")

TABLE_TS={"market_events":"event_ts","orderbook_snapshots":"ts","footprint_1m":"ts",
          "candles_1m":"ts","derivatives_metrics":"ts"}

async def cleanup_dataset_safe(pool,dataset,retention_days,batch_size=10000):
    if dataset not in TABLE_TS:raise ValueError("unsupported dataset")
    ts=TABLE_TS[dataset]; deleted=0
    sql=f"""WITH doomed AS (
      SELECT t.ctid FROM {dataset} t
      JOIN (
        SELECT symbol,min(consumed_through) safe_through
        FROM consumer_watermarks WHERE dataset=$3 AND required=true GROUP BY symbol
      ) w ON w.symbol=t.symbol
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
        while True:
            r=await c.execute(sql,int(retention_days),int(batch_size),dataset)
            n=int(r.split()[-1]);deleted+=n
            if n<int(batch_size):break
            await asyncio.sleep(.05)
    return deleted
