import asyncio, logging, os
from datetime import timedelta
log=logging.getLogger("retention")

RETENTION_DEFAULTS={
    "market_events": 7,
    "orderbook_snapshots": 14,
    "footprint_1m": 90,
    "candles_1m": 3650,
    "derivatives_metrics": 365,
}

async def ensure_retention_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS analysis_watermarks(
          dataset text NOT NULL,
          symbol text NOT NULL,
          analyzed_through timestamptz NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY(dataset,symbol)
        );
        CREATE TABLE IF NOT EXISTS retention_runs(
          id bigserial PRIMARY KEY,
          started_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz,
          dataset text NOT NULL,
          deleted_rows bigint NOT NULL DEFAULT 0,
          cutoff timestamptz,
          status text NOT NULL,
          details jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        """)

async def set_watermark(pool,dataset,symbol,analyzed_through):
    async with pool.acquire() as c:
        await c.execute("""
        INSERT INTO analysis_watermarks(dataset,symbol,analyzed_through)
        VALUES($1,$2,$3)
        ON CONFLICT(dataset,symbol) DO UPDATE SET
          analyzed_through=GREATEST(analysis_watermarks.analyzed_through,EXCLUDED.analyzed_through),
          updated_at=now()
        """,dataset,symbol,analyzed_through)

async def cleanup_dataset(pool,dataset,retention_days,batch_size=10000):
    if dataset not in RETENTION_DEFAULTS:
        raise ValueError(f"unsupported dataset {dataset}")
    deleted=0
    async with pool.acquire() as c:
        run_id=await c.fetchval("""INSERT INTO retention_runs(dataset,status) VALUES($1,'running') RETURNING id""",dataset)
        try:
            if dataset=="market_events":
                sql="""
                WITH doomed AS (
                  SELECT me.ctid
                  FROM market_events me
                  JOIN analysis_watermarks w
                    ON w.dataset='market_events' AND w.symbol=me.symbol
                  WHERE me.event_ts < now() - ($1::int * interval '1 day')
                    AND me.event_ts <= w.analyzed_through
                  LIMIT $2
                )
                DELETE FROM market_events me USING doomed d WHERE me.ctid=d.ctid
                """
            else:
                tscol="ts"
                sql=f"""
                WITH doomed AS (
                  SELECT t.ctid
                  FROM {dataset} t
                  JOIN analysis_watermarks w
                    ON w.dataset=$3 AND w.symbol=t.symbol
                  WHERE t.{tscol} < now() - ($1::int * interval '1 day')
                    AND t.{tscol} <= w.analyzed_through
                  LIMIT $2
                )
                DELETE FROM {dataset} t USING doomed d WHERE t.ctid=d.ctid
                """
            while True:
                if dataset=="market_events":
                    result=await c.execute(sql,retention_days,batch_size)
                else:
                    result=await c.execute(sql,retention_days,batch_size,dataset)
                n=int(result.split()[-1])
                deleted+=n
                if n < batch_size: break
                await asyncio.sleep(0.05)
            await c.execute("""UPDATE retention_runs SET finished_at=now(),deleted_rows=$2,status='ok'
                               WHERE id=$1""",run_id,deleted)
            return deleted
        except Exception as e:
            await c.execute("""UPDATE retention_runs SET finished_at=now(),status='failed',
                               details=jsonb_build_object('error',$2) WHERE id=$1""",run_id,str(e))
            raise

async def cleanup_all(pool,overrides=None):
    cfg=dict(RETENTION_DEFAULTS)
    if overrides: cfg.update(overrides)
    out={}
    for dataset,days in cfg.items():
        out[dataset]=await cleanup_dataset(pool,dataset,days)
    return out


async def retention_scheduler(pool,settings):
    if not settings.retention_enabled:
        log.info("retention disabled",extra={"event":"retention_disabled"})
        return
    overrides={
        "market_events":settings.retention_market_events_days,
        "orderbook_snapshots":settings.retention_orderbook_snapshots_days,
        "footprint_1m":settings.retention_footprint_days,
        "derivatives_metrics":settings.retention_derivatives_days,
    }
    while True:
        try:
            result=await cleanup_all(pool,overrides)
            log.info("automatic retention completed",extra={
                "event":"retention_complete",
                "component":str(result)
            })
        except Exception:
            log.exception("automatic retention failed",extra={"event":"retention_failed"})
        await asyncio.sleep(max(5,settings.retention_interval_minutes)*60)
