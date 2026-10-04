from __future__ import annotations


async def startup_status(pool):
    gate=await pool.fetchrow("SELECT state,reason,updated_at FROM system_runtime WHERE singleton=TRUE")
    counts={}
    queries={
      "registered_nodes":"SELECT count(*) FROM agent_credentials WHERE revoked_at IS NULL",
      "ohlcv_rows":"SELECT count(*) FROM ohlcv_1m",
      "trade_candles":"SELECT count(*) FROM candles_1m",
      "features":"SELECT count(*) FROM market_features_1m",
      "archive_discovered":"SELECT count(*) FROM trade_archive_backfill",
      "archive_materialized":"SELECT count(*) FROM archive_compute_jobs WHERE materialized_at IS NOT NULL",
      "backfill_pending":"SELECT count(*) FROM market_backfill_state WHERE status IN ('queued','retry','running')",
      "archive_pending":"SELECT count(*) FROM archive_compute_jobs WHERE status IN ('queued','running','done') AND materialized_at IS NULL",
    }
    for key,sql in queries.items():
        counts[key]=int(await pool.fetchval(sql) or 0)
    phase="INFRA"
    if gate and str(gate["state"])=="ACTIVE":phase="COLLECTING"
    if counts["ohlcv_rows"]>0:phase="HISTORY"
    if counts["trade_candles"]>0:phase="MARKET_DATA"
    if counts["features"]>0:phase="ANALYSIS_READY"
    return {"phase":phase,"runtime_state":str(gate["state"]) if gate else "UNKNOWN",
            "runtime_reason":str(gate["reason"] or "") if gate else "",**counts}
