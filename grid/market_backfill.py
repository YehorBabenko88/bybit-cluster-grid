import asyncio,time,aiohttp

async def seed_backfill(pool,symbols,timeframe="1"):
    async with pool.acquire() as c:
        async with c.transaction():
            for x in symbols:
                symbol=x["symbol"] if isinstance(x,dict) else str(x)
                await c.execute("""INSERT INTO market_backfill_state(symbol,timeframe,status)
                  VALUES($1,$2,'queued') ON CONFLICT(symbol,timeframe) DO NOTHING""",symbol,str(timeframe))

async def claim_backfill(pool):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM market_backfill_state
              WHERE status IN ('queued','retry') ORDER BY updated_at
              FOR UPDATE SKIP LOCKED LIMIT 1""")
            if not row:return None
            await c.execute("""UPDATE market_backfill_state SET status='running',
              attempts=attempts+1,updated_at=now(),last_error=NULL
              WHERE symbol=$1 AND timeframe=$2""",row["symbol"],row["timeframe"])
            return dict(row)

async def fetch_kline_page(base_url,symbol,interval="1",end_ms=None,limit=1000):
    params={"category":"linear","symbol":symbol,"interval":str(interval),"limit":int(limit)}
    if end_ms:params["end"]=int(end_ms)
    async with aiohttp.ClientSession() as s:
        async with s.get(base_url+"/v5/market/kline",params=params,timeout=30) as r:
            r.raise_for_status();j=await r.json()
    if j.get("retCode")!=0:raise RuntimeError(f"Bybit kline: {j.get('retMsg')}")
    return j.get("result",{}).get("list",[])

async def store_kline_page(pool,symbol,rows):
    if not rows:return None
    from datetime import datetime,timezone
    parsed=[]
    for r in rows:
        ts=datetime.fromtimestamp(int(r[0])/1000,timezone.utc)
        parsed.append((symbol,ts,r[1],r[2],r[3],r[4],r[5],r[6] if len(r)>6 else None))
    async with pool.acquire() as c:
        async with c.transaction():
            await c.executemany("""INSERT INTO candles_1m(symbol,ts,open,high,low,close,volume,turnover)
              VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(symbol,ts) DO NOTHING""",parsed)
    return min(x[1] for x in parsed),max(x[1] for x in parsed)

async def backfill_symbol(pool,base_url,state,max_pages=50,pause=.08):
    symbol=state["symbol"];end_ms=state.get("next_end_ms");oldest=newest=None
    for _ in range(int(max_pages)):
        rows=await fetch_kline_page(base_url,symbol,state.get("timeframe","1"),end_ms)
        if not rows:break
        lo,hi=await store_kline_page(pool,symbol,rows)
        oldest=lo if oldest is None else min(oldest,lo);newest=hi if newest is None else max(newest,hi)
        next_end=int(lo.timestamp()*1000)-1
        if end_ms is not None and next_end>=end_ms:break
        end_ms=next_end
        await asyncio.sleep(float(pause))
    await pool.execute("""UPDATE market_backfill_state SET status='done',
      oldest_loaded_ts=COALESCE($3,oldest_loaded_ts),newest_loaded_ts=COALESCE($4,newest_loaded_ts),
      next_end_ms=$5,updated_at=now() WHERE symbol=$1 AND timeframe=$2""",
      symbol,state.get("timeframe","1"),oldest,newest,end_ms)
    return {"symbol":symbol,"oldest":oldest,"newest":newest}
