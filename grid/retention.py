import asyncio, logging, os
from datetime import timedelta
from .retention_v2 import cleanup_dataset_safe,retention_backlog
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
    """Compatibility entry point. All deletion is consumer-safe and hold-aware."""
    if dataset not in RETENTION_DEFAULTS:
        raise ValueError(f"unsupported dataset {dataset}")
    return await cleanup_dataset_safe(pool,dataset,retention_days,batch_size)

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
            backlog={}
            for dataset,days in dict(RETENTION_DEFAULTS,**overrides).items():
                backlog[dataset]=await retention_backlog(pool,dataset,days)
            blocked={k:v for k,v in backlog.items() if v>0}
            if blocked:
                log.warning("retention backlog remains past policy age",extra={
                    "event":"retention_backlog","component":str(blocked)})
            log.info("automatic retention completed",extra={
                "event":"retention_complete",
                "component":str({"deleted":result,"backlog":backlog})
            })
        except Exception:
            log.exception("automatic retention failed",extra={"event":"retention_failed"})
        await asyncio.sleep(max(5,settings.retention_interval_minutes)*60)
