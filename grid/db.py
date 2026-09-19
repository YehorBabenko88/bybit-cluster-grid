import asyncpg, json, logging
from .config import settings
log=logging.getLogger("db")

class Database:
    def __init__(self): self.pool=None
    async def connect(self):
        self.pool=await asyncpg.create_pool(settings.postgres_dsn,min_size=1,max_size=10,command_timeout=30)
    async def ensure_schema(self):
        async with self.pool.acquire() as c:
            await c.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations(
              version bigint PRIMARY KEY, name text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS market_events(
              id bigserial PRIMARY KEY,
              symbol text NOT NULL,
              event_ts timestamptz NOT NULL,
              event_type text NOT NULL,
              source text NOT NULL DEFAULT 'bybit',
              payload jsonb NOT NULL,
              ingest_ts timestamptz NOT NULL DEFAULT now(),
              UNIQUE(symbol,event_ts,event_type,payload)
            );
            CREATE INDEX IF NOT EXISTS market_events_symbol_ts_idx ON market_events(symbol,event_ts DESC);
            CREATE INDEX IF NOT EXISTS market_events_payload_gin_idx ON market_events USING gin(payload);

            CREATE TABLE IF NOT EXISTS candles_1m(
              symbol text NOT NULL, ts timestamptz NOT NULL,
              open numeric, high numeric, low numeric, close numeric,
              buy_volume numeric, sell_volume numeric, delta numeric,
              trade_count integer, poc_price numeric,
              extra jsonb NOT NULL DEFAULT '{}'::jsonb,
              PRIMARY KEY(symbol,ts)
            );

            CREATE TABLE IF NOT EXISTS footprint_1m(
              symbol text NOT NULL, ts timestamptz NOT NULL, price numeric NOT NULL,
              buy_volume numeric, sell_volume numeric, delta numeric, volume numeric,
              buy_count integer, sell_count integer,
              extra jsonb NOT NULL DEFAULT '{}'::jsonb,
              PRIMARY KEY(symbol,ts,price)
            );

            CREATE TABLE IF NOT EXISTS orderbook_snapshots(
              symbol text NOT NULL, ts timestamptz NOT NULL,
              best_bid numeric, best_ask numeric, spread numeric,
              bid_depth numeric, ask_depth numeric, imbalance numeric,
              walls jsonb NOT NULL DEFAULT '[]'::jsonb,
              book jsonb NOT NULL DEFAULT '{}'::jsonb,
              extra jsonb NOT NULL DEFAULT '{}'::jsonb,
              PRIMARY KEY(symbol,ts)
            );

            CREATE TABLE IF NOT EXISTS derivatives_metrics(
              symbol text NOT NULL, ts timestamptz NOT NULL,
              open_interest numeric, funding_rate numeric, mark_price numeric,
              index_price numeric, basis numeric,
              extra jsonb NOT NULL DEFAULT '{}'::jsonb,
              PRIMARY KEY(symbol,ts)
            );
            """)
    async def insert_event(self,symbol,event_ts,event_type,payload):
        async with self.pool.acquire() as c:
            await c.execute("""INSERT INTO market_events(symbol,event_ts,event_type,payload)
            VALUES($1,to_timestamp($2/1000.0),$3,$4::jsonb)
            ON CONFLICT DO NOTHING""",symbol,event_ts,event_type,json.dumps(payload))
