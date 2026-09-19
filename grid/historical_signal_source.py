async def load_poc_signals(pool,symbol,start_ts=None,end_ts=None):
    return await pool.fetch("""SELECT p.symbol,p.first_touch_ts AS event_ts,'POC'::text setup_type,
      p.poc_price::double precision entry_ref,p.source_regime AS regime,
      p.source_ts,p.first_touch_kind,COALESCE(f.regime,p.source_regime,'UNKNOWN') market_state
      FROM poc_lifecycle p
      LEFT JOIN market_features_1m f ON f.symbol=p.symbol AND f.ts=p.first_touch_ts
      WHERE p.symbol=$1 AND p.first_touch_ts IS NOT NULL
      AND ($2::timestamptz IS NULL OR p.first_touch_ts>=$2)
      AND ($3::timestamptz IS NULL OR p.first_touch_ts<$3)
      ORDER BY p.first_touch_ts""",symbol,start_ts,end_ts)

async def load_level_signals(pool,symbol,setup_type,start_ts=None,end_ts=None):
    event_type="ACCEPTED_BREAK" if setup_type=="BREAKOUT" else "FALSE_BREAK"
    return await pool.fetch("""SELECT e.symbol,e.event_ts,$2::text setup_type,
      e.level_price::double precision entry_ref,
      COALESCE(f.regime,'UNKNOWN') regime,COALESCE(f.regime,'UNKNOWN') market_state,
      e.timeframe,e.level_kind,e.direction,e.event_type
      FROM level_events e
      LEFT JOIN market_features_1m f ON f.symbol=e.symbol AND f.ts=e.event_ts
      WHERE e.symbol=$1 AND e.event_type=$3
      AND ($4::timestamptz IS NULL OR e.event_ts>=$4)
      AND ($5::timestamptz IS NULL OR e.event_ts<$5)
      ORDER BY e.event_ts""",symbol,setup_type,event_type,start_ts,end_ts)

async def load_volatility_signals(pool,symbol,start_ts=None,end_ts=None):
    return await pool.fetch("""WITH x AS (
      SELECT symbol,ts,regime,features,
      lag(regime) OVER(PARTITION BY symbol ORDER BY ts) prev_regime
      FROM market_features_1m WHERE symbol=$1
      AND ($2::timestamptz IS NULL OR ts>=$2)
      AND ($3::timestamptz IS NULL OR ts<$3))
      SELECT symbol,ts AS event_ts,'VOLATILITY_CAPTURE'::text setup_type,
      NULL::double precision entry_ref,regime,regime AS market_state,prev_regime
      FROM x WHERE regime IN ('HIGH_VOL','IMPULSE')
      AND COALESCE(prev_regime,'') NOT IN ('HIGH_VOL','IMPULSE') ORDER BY ts""",
      symbol,start_ts,end_ts)

async def load_signals(pool,symbol,setup_type,start_ts=None,end_ts=None):
    if setup_type=="POC": rows=await load_poc_signals(pool,symbol,start_ts,end_ts)
    elif setup_type in ("BREAKOUT","FALSE_BREAK"):
        rows=await load_level_signals(pool,symbol,setup_type,start_ts,end_ts)
    elif setup_type=="VOLATILITY_CAPTURE":
        rows=await load_volatility_signals(pool,symbol,start_ts,end_ts)
    else: raise ValueError(f"unsupported setup_type: {setup_type}")
    return [dict(r) for r in rows]
