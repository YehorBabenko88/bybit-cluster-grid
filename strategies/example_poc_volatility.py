"""Example hot-load strategy plugin.

Contract: async def run(ctx)
This deliberately demonstrates the plugin API; it is not a trading recommendation.
"""
import json

async def run(ctx):
    job=ctx.job
    params=job["params"] if isinstance(job["params"],dict) else json.loads(job["params"])
    symbols=job["symbols"] if isinstance(job["symbols"],list) else json.loads(job["symbols"])
    threshold=float(params.get("range_pct_min",0.01))

    if not symbols:
        rows=await ctx.fetch("SELECT symbol FROM instruments WHERE status='Trading' ORDER BY symbol")
        symbols=[r["symbol"] for r in rows]

    for symbol in symbols:
        rows=await ctx.fetch("""
          SELECT ts,open,high,low,close,poc_price,delta,buy_volume,sell_volume
          FROM candles_1m
          WHERE symbol=$1 AND ($2::timestamptz IS NULL OR ts >= $2)
            AND ($3::timestamptz IS NULL OR ts <= $3)
          ORDER BY ts
        """,symbol,job["start_ts"],job["end_ts"])
        for r in rows:
            close=float(r["close"] or 0)
            if not close: continue
            range_pct=(float(r["high"])-float(r["low"]))/close
            if range_pct < threshold: continue
            await ctx.emit(symbol,r["ts"],"volatile_poc_candidate",{
                "range_pct":range_pct,
                "poc_price":float(r["poc_price"]) if r["poc_price"] is not None else None,
                "delta":float(r["delta"] or 0),
                "volume":float(r["buy_volume"] or 0)+float(r["sell_volume"] or 0),
            })
