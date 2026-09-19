CAPS=("ohlcv_history","trade_history","live_trades","live_orderbook","footprint_history","orderbook_history")
VALID={"UNKNOWN","QUEUED","PARTIAL","READY","LIVE","UNAVAILABLE","ERROR"}

async def ensure_symbol(pool,symbol):
    await pool.execute("INSERT INTO market_data_capabilities(symbol) VALUES($1) ON CONFLICT DO NOTHING",symbol)

async def set_capability(pool,symbol,field,status,details=None):
    if field not in CAPS:raise ValueError("unknown capability")
    if status not in VALID:raise ValueError("invalid capability status")
    await ensure_symbol(pool,symbol)
    await pool.execute(f"""UPDATE market_data_capabilities SET {field}=$2,
      details=details||$3::jsonb,updated_at=now() WHERE symbol=$1""",
      symbol,status,__import__("json").dumps(details or {}))

async def capability(pool,symbol):
    row=await pool.fetchrow("SELECT * FROM market_data_capabilities WHERE symbol=$1",symbol)
    return dict(row) if row else None

def feature_permissions(c):
    c=c or {}
    trades=c.get("trade_history") in ("READY","PARTIAL") or c.get("live_trades")=="LIVE"
    return {
      "volatility_history":c.get("ohlcv_history") in ("READY","PARTIAL"),
      "htf_levels_history":c.get("ohlcv_history") in ("READY","PARTIAL"),
      "delta_history":c.get("trade_history") in ("READY","PARTIAL"),
      "footprint_history":c.get("footprint_history") in ("READY","PARTIAL"),
      "poc_history":c.get("footprint_history") in ("READY","PARTIAL"),
      "live_delta":c.get("live_trades")=="LIVE",
      "live_orderbook":c.get("live_orderbook")=="LIVE",
      "historical_orderbook_microstructure":c.get("orderbook_history") in ("READY","PARTIAL"),
    }
