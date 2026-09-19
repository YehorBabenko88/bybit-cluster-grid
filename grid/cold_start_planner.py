from .data_capabilities import ensure_symbol,set_capability

async def seed_cold_start(pool,symbols):
    for item in symbols:
        symbol=item["symbol"] if isinstance(item,dict) else str(item)
        await ensure_symbol(pool,symbol)
        await pool.execute("""INSERT INTO market_backfill_state(symbol,timeframe,status)
          VALUES($1,'1','queued') ON CONFLICT(symbol,timeframe) DO NOTHING""",symbol)
        await set_capability(pool,symbol,"ohlcv_history","QUEUED")
        await set_capability(pool,symbol,"trade_history","UNKNOWN")
    return len(symbols)

async def readiness_by_research(pool):
    row=await pool.fetchrow("""SELECT
      count(*) total,
      count(*) FILTER(WHERE ohlcv_history IN ('READY','PARTIAL')) ohlcv,
      count(*) FILTER(WHERE trade_history IN ('READY','PARTIAL')) trades,
      count(*) FILTER(WHERE footprint_history IN ('READY','PARTIAL')) footprint,
      count(*) FILTER(WHERE live_trades='LIVE') live_trades,
      count(*) FILTER(WHERE live_orderbook='LIVE') live_orderbook
      FROM market_data_capabilities""")
    n=max(1,row["total"])
    return {
      "symbols":row["total"],
      "volatility_level_ready_ratio":row["ohlcv"]/n,
      "historical_delta_ready_ratio":row["trades"]/n,
      "historical_poc_ready_ratio":row["footprint"]/n,
      "live_trade_ratio":row["live_trades"]/n,
      "live_orderbook_ratio":row["live_orderbook"]/n,
    }
