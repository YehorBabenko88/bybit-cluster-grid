import logging
log=logging.getLogger("migrations")

MIGRATIONS=[
(1,"baseline_jsonb_extensible",[
"ALTER TABLE candles_1m ADD COLUMN IF NOT EXISTS extra jsonb NOT NULL DEFAULT '{}'::jsonb",
"ALTER TABLE footprint_1m ADD COLUMN IF NOT EXISTS extra jsonb NOT NULL DEFAULT '{}'::jsonb",
]),
(2,"market_microstructure_tables",[
"""CREATE TABLE IF NOT EXISTS orderbook_snapshots(
symbol text NOT NULL, ts timestamptz NOT NULL, best_bid numeric, best_ask numeric, spread numeric,
bid_depth numeric, ask_depth numeric, imbalance numeric, walls jsonb NOT NULL DEFAULT '[]'::jsonb,
book jsonb NOT NULL DEFAULT '{}'::jsonb, extra jsonb NOT NULL DEFAULT '{}'::jsonb, PRIMARY KEY(symbol,ts))""",
"""CREATE TABLE IF NOT EXISTS derivatives_metrics(
symbol text NOT NULL, ts timestamptz NOT NULL, open_interest numeric, funding_rate numeric,
mark_price numeric, index_price numeric, basis numeric, extra jsonb NOT NULL DEFAULT '{}'::jsonb,
PRIMARY KEY(symbol,ts))"""
]),
(3,"minute_data_quality",[
"ALTER TABLE candles_1m ADD COLUMN IF NOT EXISTS quality_status text NOT NULL DEFAULT 'UNKNOWN'",
"ALTER TABLE candles_1m ADD COLUMN IF NOT EXISTS quality_reasons jsonb NOT NULL DEFAULT '[]'::jsonb",
"CREATE INDEX IF NOT EXISTS candles_1m_quality_idx ON candles_1m(quality_status,ts DESC)"
]),
(4,"market_features_1m",[
"""CREATE TABLE IF NOT EXISTS market_features_1m(
symbol text NOT NULL, ts timestamptz NOT NULL, eligible boolean NOT NULL,
quality_status text NOT NULL, features jsonb NOT NULL, capabilities jsonb NOT NULL,
built_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(symbol,ts))""",
"CREATE INDEX IF NOT EXISTS market_features_1m_eligible_idx ON market_features_1m(eligible,ts DESC)"
])
]

async def apply_migrations(pool):
    async with pool.acquire() as c:
        await c.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
        version bigint PRIMARY KEY,name text NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())""")
        rows=await c.fetch("SELECT version FROM schema_migrations")
        done={r["version"] for r in rows}
        for version,name,sqls in MIGRATIONS:
            if version in done: continue
            async with c.transaction():
                for sql in sqls: await c.execute(sql)
                await c.execute("INSERT INTO schema_migrations(version,name) VALUES($1,$2)",version,name)
            log.info("migration applied",extra={"event":"migration","component":name})
