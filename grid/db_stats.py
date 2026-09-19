async def database_stats(pool):
    async with pool.acquire() as c:
        db=await c.fetchrow("""
        SELECT current_database() AS name,
               pg_database_size(current_database()) AS bytes,
               pg_size_pretty(pg_database_size(current_database())) AS pretty
        """)
        tables=await c.fetch("""
        SELECT relname AS table_name,
               pg_total_relation_size(relid) AS bytes,
               pg_size_pretty(pg_total_relation_size(relid)) AS pretty
        FROM pg_catalog.pg_statio_user_tables
        ORDER BY pg_total_relation_size(relid) DESC
        LIMIT 20
        """)
        counts={}
        for t in ("market_events","orderbook_snapshots","derivatives_metrics","footprint_1m","candles_1m"):
            try:
                counts[t]=await c.fetchval(f"SELECT count(*) FROM {t}")
            except Exception:
                counts[t]=None
        pending=await c.fetch("""
        SELECT dataset,
               count(*) AS symbols,
               min(analyzed_through) AS min_watermark,
               max(analyzed_through) AS max_watermark
        FROM analysis_watermarks
        GROUP BY dataset
        ORDER BY dataset
        """)
        return {
            "database":dict(db),
            "tables":[dict(x) for x in tables],
            "counts":counts,
            "watermarks":[dict(x) for x in pending],
        }
