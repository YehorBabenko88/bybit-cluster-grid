from .retention_v2 import TABLE_TS

async def cleanup_plan(pool,dataset,retention_days):
    if dataset not in TABLE_TS:raise ValueError("unsupported dataset")
    ts=TABLE_TS[dataset]
    required=await pool.fetch("""SELECT consumer FROM retention_consumers
      WHERE dataset=$1 AND required=true AND active=true ORDER BY consumer""",dataset)
    if not required:
        return {"dataset":dataset,"deletable":0,"blocked":"no_required_consumers"}
    missing=await pool.fetchval(f"""SELECT count(*) FROM (
      SELECT DISTINCT t.symbol,rc.consumer FROM {dataset} t
      CROSS JOIN retention_consumers rc
      LEFT JOIN consumer_watermarks cw ON cw.dataset=rc.dataset AND cw.consumer=rc.consumer AND cw.symbol=t.symbol
      WHERE rc.dataset=$1 AND rc.required=true AND rc.active=true AND cw.consumed_through IS NULL
    ) x""",dataset)
    if missing:
        return {"dataset":dataset,"deletable":0,"blocked":"missing_watermarks","missing":int(missing)}
    count=await pool.fetchval(f"""WITH safe AS (
      SELECT t.symbol,min(cw.consumed_through) safe_through FROM {dataset} t
      CROSS JOIN retention_consumers rc
      JOIN consumer_watermarks cw ON cw.dataset=rc.dataset AND cw.consumer=rc.consumer AND cw.symbol=t.symbol
      WHERE rc.dataset=$1 AND rc.required=true AND rc.active=true GROUP BY t.symbol
    ) SELECT count(*) FROM {dataset} t JOIN safe s ON s.symbol=t.symbol
      WHERE t.{ts}<now()-($2::int*interval '1 day') AND t.{ts}<=s.safe_through
      AND NOT EXISTS(SELECT 1 FROM retention_holds h WHERE h.dataset=$1
        AND (h.symbol IS NULL OR h.symbol=t.symbol) AND (h.expires_at IS NULL OR h.expires_at>now())
        AND (h.from_ts IS NULL OR t.{ts}>=h.from_ts) AND (h.through_ts IS NULL OR t.{ts}<=h.through_ts))""",
      dataset,int(retention_days))
    return {"dataset":dataset,"deletable":int(count or 0),"blocked":None}
