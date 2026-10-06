async def store_derived_minute(conn,row):
    accepted=await conn.fetchval("""INSERT INTO candles_1m
      (symbol,ts,open,high,low,close,buy_volume,sell_volume,delta,trade_count,poc_price,quality_status,quality_reasons)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'ARCHIVE', '[]'::jsonb)
      ON CONFLICT(symbol,ts) DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,
      close=EXCLUDED.close,buy_volume=EXCLUDED.buy_volume,sell_volume=EXCLUDED.sell_volume,
      delta=EXCLUDED.delta,trade_count=EXCLUDED.trade_count,poc_price=EXCLUDED.poc_price,
      quality_status='ARCHIVE',quality_reasons='[]'::jsonb
      WHERE EXCLUDED.trade_count >= candles_1m.trade_count
      RETURNING TRUE""",
      row["symbol"],row["ts"],row["open"],row["high"],row["low"],row["close"],
      row["buy_volume"],row["sell_volume"],row["delta"],row["trade_count"],row["poc_price"])
    if not accepted:
        return False
    # Footprint is one versioned object with its candle. Replace the complete
    # minute so levels from an older/live aggregation cannot survive as ghosts.
    await conn.execute("DELETE FROM footprint_1m WHERE symbol=$1 AND ts=$2",row["symbol"],row["ts"])
    values=[]
    for price,x in row["levels"].items():
        buy=x["buy"];sell=x["sell"]
        values.append((row["symbol"],row["ts"],price,buy,sell,buy-sell,buy+sell,x["buy_count"],x["sell_count"]))
    if values:
        await conn.executemany("""INSERT INTO footprint_1m
          (symbol,ts,price,buy_volume,sell_volume,delta,volume,buy_count,sell_count)
          VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""",values)
    return True

async def materialize_archive(pool,aggregates):
    candles=levels=0;min_ts=max_ts=None
    async with pool.acquire() as c:
        async with c.transaction():
            for row in aggregates:
                await store_derived_minute(c,row);candles+=1;levels+=len(row["levels"])
                min_ts=row["ts"] if min_ts is None else min(min_ts,row["ts"])
                max_ts=row["ts"] if max_ts is None else max(max_ts,row["ts"])
    return {"derived_candles":candles,"derived_footprint_rows":levels,"min_ts":min_ts,"max_ts":max_ts}

async def materialize_archive_stream(pool,aggregates,batch_minutes=30):
    candles=levels=source_rows=0;min_ts=max_ts=None;batch=[]
    async def flush(items):
        nonlocal candles,levels,source_rows,min_ts,max_ts
        if not items:return
        async with pool.acquire() as c:
            async with c.transaction():
                for row in items:
                    await store_derived_minute(c,row)
                    candles+=1;levels+=len(row["levels"]);source_rows+=int(row["trade_count"])
                    min_ts=row["ts"] if min_ts is None else min(min_ts,row["ts"])
                    max_ts=row["ts"] if max_ts is None else max(max_ts,row["ts"])
    for row in aggregates:
        batch.append(row)
        if len(batch)>=int(batch_minutes):
            await flush(batch);batch=[]
    await flush(batch)
    return {"source_rows":source_rows,"derived_candles":candles,
            "derived_footprint_rows":levels,"min_ts":min_ts,"max_ts":max_ts}
