def _direction(signal,candle):
    d=(signal.get("direction") or "").upper()
    if d in ("UP","LONG","BULL","ABOVE"):return 1
    if d in ("DOWN","SHORT","BEAR","BELOW"):return -1
    # POC/volatility fallback: use first post-signal candle direction.
    return 1 if float(candle["close"])>=float(candle["open"]) else -1

def _cost(notional_bps,price):
    return abs(float(price))*float(notional_bps)/10000.0

def simulate_barrier(signal,candles,tp_bps=40,sl_bps=25,horizon_bars=60,
                     fee_bps=5.5,slippage_bps=1.5,notional=100.0):
    if not candles:return None
    rows=list(candles)[:int(horizon_bars)]
    first=rows[0]
    entry=float(signal.get("entry_ref") or first["open"])
    side=_direction(signal,first)
    tp=entry*(1+side*float(tp_bps)/10000.0)
    sl=entry*(1-side*float(sl_bps)/10000.0)
    exit_price=float(rows[-1]["close"]);exit_ts=rows[-1]["ts"];reason="HORIZON"
    max_fav=0.0;max_adv=0.0
    for c in rows:
        hi=float(c["high"]);lo=float(c["low"])
        fav=(hi-entry)*side if side>0 else (entry-lo)
        adv=(entry-lo) if side>0 else (hi-entry)
        max_fav=max(max_fav,fav);max_adv=max(max_adv,adv)
        hit_tp=(hi>=tp if side>0 else lo<=tp)
        hit_sl=(lo<=sl if side>0 else hi>=sl)
        # Conservative same-bar tie: assume stop first to avoid optimistic bias.
        if hit_tp and hit_sl:
            exit_price=sl;exit_ts=c["ts"];reason="SL_SAME_BAR";break
        if hit_sl:
            exit_price=sl;exit_ts=c["ts"];reason="SL";break
        if hit_tp:
            exit_price=tp;exit_ts=c["ts"];reason="TP";break
    notional=float(notional)
    if notional<=0:raise ValueError("notional must be positive")
    qty=notional/entry
    gross=(exit_price-entry)*side*qty
    fees=notional*float(fee_bps)/10000.0 + abs(exit_price*qty)*float(fee_bps)/10000.0
    slippage=notional*float(slippage_bps)/10000.0 + abs(exit_price*qty)*float(slippage_bps)/10000.0
    return {
      "signal_id":signal.get("signal_id"),"symbol":signal.get("symbol"),
      "setup_type":signal.get("setup_type"),"regime":signal.get("regime"),
      "event_ts":signal.get("event_ts"),"entry":entry,"exit":exit_price,
      "notional":notional,"quantity":qty,"initial_tp":tp,"initial_sl":sl,
      "exit_ts":exit_ts,"side":"LONG" if side>0 else "SHORT","exit_reason":reason,
      "pnl":gross,"fees":fees,"slippage":slippage,
      "mfe":max_fav*qty,"mae":-max_adv*qty,"bars":len(rows)
    }

async def load_forward_candles(pool,symbol,event_ts,horizon_bars):
    rows=await pool.fetch("""SELECT ts,open,high,low,close FROM candles_1m
      WHERE symbol=$1 AND ts>=$2 ORDER BY ts LIMIT $3""",symbol,event_ts,int(horizon_bars))
    return [dict(r) for r in rows]
