CREATE TABLE IF NOT EXISTS nodes (
  node_id text PRIMARY KEY, hostname text, last_seen timestamptz NOT NULL DEFAULT now(),
  cpu_pct double precision, ram_pct double precision, disk_free bigint, assigned_symbols integer DEFAULT 0
);
CREATE TABLE IF NOT EXISTS candles_1m (
  symbol text NOT NULL, ts timestamptz NOT NULL, open numeric NOT NULL, high numeric NOT NULL,
  low numeric NOT NULL, close numeric NOT NULL, buy_volume numeric NOT NULL, sell_volume numeric NOT NULL,
  delta numeric NOT NULL, trade_count integer NOT NULL, poc_price numeric,
  PRIMARY KEY(symbol, ts)
);
CREATE TABLE IF NOT EXISTS footprint_1m (
  symbol text NOT NULL, ts timestamptz NOT NULL, price numeric NOT NULL,
  buy_volume numeric NOT NULL, sell_volume numeric NOT NULL, delta numeric NOT NULL,
  volume numeric NOT NULL, buy_count integer NOT NULL, sell_count integer NOT NULL,
  PRIMARY KEY(symbol, ts, price)
);
CREATE INDEX IF NOT EXISTS footprint_1m_symbol_ts_idx ON footprint_1m(symbol, ts DESC);
