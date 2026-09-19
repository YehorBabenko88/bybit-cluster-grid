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
            row=await c.fetchrow("""SELECT b.*,
              COALESCE(NULLIF(i.metadata->>'launch_time','')::bigint,0) AS launch_time_ms
              FROM market_backfill_state b
              LEFT JOIN instruments i ON i.symbol=b.symbol
              WHERE b.status IN ('queued','retry') ORDER BY b.updated_at
              FOR UPDATE OF b SKIP LOCKED LIMIT 1""")
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
            await c.executemany("""INSERT INTO ohlcv_1m(symbol,ts,open,high,low,close,volume,turnover)
              VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(symbol,ts) DO NOTHING""",parsed)
    return min(x[1] for x in parsed),max(x[1] for x in parsed)

async def backfill_symbol(pool,base_url,state,max_pages=50,pause=.08):
    symbol=state["symbol"];end_ms=state.get("next_end_ms");oldest=newest=None
    launch_ms=int(state.get("launch_time_ms") or 0)
    complete=False;pages=0
    for _ in range(int(max_pages)):
        rows=await fetch_kline_page(base_url,symbol,state.get("timeframe","1"),end_ms)
        pages+=1
        if not rows:
            complete=True
            break
        lo,hi=await store_kline_page(pool,symbol,rows)
        oldest=lo if oldest is None else min(oldest,lo);newest=hi if newest is None else max(newest,hi)
        lo_ms=int(lo.timestamp()*1000)
        next_end=lo_ms-1
        if launch_ms and lo_ms<=launch_ms:
            complete=True;end_ms=next_end;break
        if len(rows)<1000:
            complete=True;end_ms=next_end;break
        if end_ms is not None and next_end>=int(end_ms):
            raise RuntimeError(f"OHLCV backfill stalled for {symbol}")
        end_ms=next_end
        await asyncio.sleep(float(pause))
    status="done" if complete else "queued"
    await pool.execute("""UPDATE market_backfill_state SET status=$3,
      oldest_loaded_ts=CASE WHEN $4::timestamptz IS NULL THEN oldest_loaded_ts
        ELSE LEAST(COALESCE(oldest_loaded_ts,$4),$4) END,
      newest_loaded_ts=CASE WHEN $5::timestamptz IS NULL THEN newest_loaded_ts
        ELSE GREATEST(COALESCE(newest_loaded_ts,$5),$5) END,
      next_end_ms=$6,updated_at=now(),last_error=NULL WHERE symbol=$1 AND timeframe=$2""",
      symbol,state.get("timeframe","1"),status,oldest,newest,end_ms)
    return {"symbol":symbol,"oldest":oldest,"newest":newest,"complete":complete,"pages":pages}

async def run_backfill_worker(pool,base_url,stop_event=None,max_pages=50):
    from .data_capabilities import set_capability
    stop_event=stop_event or asyncio.Event();done=chunks=failed=0
    while not stop_event.is_set():
        state=await claim_backfill(pool)
        if not state:break
        try:
            r=await backfill_symbol(pool,base_url,state,max_pages=max_pages)
            chunks+=1
            if r["complete"]:
                done+=1
                await set_capability(pool,state["symbol"],"ohlcv_history","READY",
                                     {"source":"bybit_rest","backfill":"complete"})
            else:
                await set_capability(pool,state["symbol"],"ohlcv_history","PARTIAL",
                                     {"source":"bybit_rest","backfill":"continuing"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failed+=1
            await pool.execute("""UPDATE market_backfill_state SET status='retry',last_error=$3,
              updated_at=now() WHERE symbol=$1 AND timeframe=$2""",
              state["symbol"],state.get("timeframe","1"),str(exc)[:4000])
    return {"completed":done,"chunks":chunks,"failed":failed}
