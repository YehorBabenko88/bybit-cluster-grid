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
              WHERE b.status IN ('queued','retry') AND COALESCE(i.status,'Retired')='Trading'
              ORDER BY b.updated_at
              FOR UPDATE OF b SKIP LOCKED LIMIT 1""")
            if not row:return None
            await c.execute("""UPDATE market_backfill_state SET status='running',
              attempts=attempts+1,updated_at=now(),last_error=NULL
              WHERE symbol=$1 AND timeframe=$2""",row["symbol"],row["timeframe"])
            return dict(row)

async def fetch_kline_page(base_url,symbol,interval="1",end_ms=None,limit=1000,*,start_ms=None,dataset="candles"):
    """One bounded public REST path for backfill and explicitly ranged reads.

    The caller owns pagination and durable state. This function neither writes
    candles nor declares history complete when Bybit returns a short/empty page.
    Price-series datasets are read-only pages; they must not enter the OHLCV writer.
    """
    from .bybit import _bounded_int, _https_origin, _read_bounded_http_response, _bounded_result

    origin=_https_origin(base_url)
    # Port Strattester's useful public price-series routes into Grid's sole
    # bounded transport, without adding a second Bybit client or writer.
    routes={"candles":"kline","mark_price":"mark-price-kline",
            "index_price":"index-price-kline",
            "premium_index":"premium-index-price-kline"}
    if type(dataset) is not str or dataset not in routes:
        raise ValueError("unsupported public kline dataset")
    _bounded_int(limit,"kline limit",1,1000)
    if end_ms is not None:
        _bounded_int(end_ms,"end_ms",0,2**63-1)
    if start_ms is not None:
        _bounded_int(start_ms,"start_ms",0,2**63-1)
        if end_ms is None or end_ms<start_ms:
            raise ValueError("invalid kline time range")
    if (not isinstance(symbol,str) or not 1<=len(symbol)<=64
            or not symbol.isascii() or not symbol.isalnum()):
        raise ValueError("invalid symbol")
    if (type(interval) not in (str,int) or not 1<=len(str(interval))<=32
            or not str(interval).isascii() or not str(interval).isalnum()):
        raise ValueError("invalid interval")

    params={"category":"linear","symbol":symbol,"interval":str(interval),"limit":limit}
    if start_ms is not None:
        params["start"]=start_ms
    if end_ms is not None:
        params["end"]=end_ms
    timeout=aiohttp.ClientTimeout(total=30,connect=10,sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout,trust_env=False,auto_decompress=False,
                                    cookie_jar=aiohttp.DummyCookieJar(),
                                    headers={"Accept-Encoding":"identity"}) as s:
        async with s.get(origin+"/v5/market/"+routes[dataset],params=params,allow_redirects=False) as r:
            raw=await _read_bounded_http_response(r)
    return _bounded_result(raw)["list"]

async def fetch_open_interest_page(base_url,symbol,interval="5min",start_ms=None,
                                   end_ms=None,limit=200):
    """One bounded public OI page using Grid's existing Bybit transport.

    Meta Analyse previously owned an independent OI reader and Decimal parser.
    This is read-only retrieval; page data is not asserted complete or live,
    and cannot directly write the candle or derivatives tables.
    """
    from decimal import Decimal,InvalidOperation
    from .bybit import _bounded_int,_https_origin,_read_bounded_http_response,_bounded_result

    origin=_https_origin(base_url)
    if type(symbol) is not str or not 1<=len(symbol)<=64 or not symbol.isascii() or not symbol.isalnum():
        raise ValueError("invalid OI symbol")
    if type(interval) is not str or interval not in ("5min","15min","30min","1h","4h","1d"):
        raise ValueError("unsupported OI interval")
    _bounded_int(limit,"open interest page limit",1,200)
    if start_ms is not None:
        _bounded_int(start_ms,"OI start_ms",0,2**63-1)
    if end_ms is not None:
        _bounded_int(end_ms,"OI end_ms",0,2**63-1)
    if start_ms is not None and end_ms is not None and end_ms<start_ms:
        raise ValueError("invalid OI time range")
    params={"category":"linear","symbol":symbol,"intervalTime":interval,"limit":limit}
    if start_ms is not None:
        params["startTime"]=start_ms
    if end_ms is not None:
        params["endTime"]=end_ms
    timeout=aiohttp.ClientTimeout(total=30,connect=10,sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout,trust_env=False,auto_decompress=False,
                                    cookie_jar=aiohttp.DummyCookieJar(),
                                    headers={"Accept-Encoding":"identity"}) as s:
        async with s.get(origin+"/v5/market/open-interest",params=params,allow_redirects=False) as r:
            raw=await _read_bounded_http_response(r)
    rows=_bounded_result(raw)["list"]
    if len(rows)>limit:
        raise ValueError("open interest page exceeds request limit")
    parsed=[]
    for row in rows:
        if type(row) is not dict:
            raise ValueError("invalid OI row")
        ts=row.get("timestamp")
        if type(ts) is str and 1<=len(ts)<=19 and ts.isascii() and ts.isdecimal():
            ts=int(ts)
        if type(ts) is not int or not 0<ts<=2**63-1:
            raise ValueError("invalid OI timestamp")
        value=row.get("openInterest")
        if type(value) is not str or not 1<=len(value)<=80:
            raise ValueError("invalid OI numeric representation")
        try:
            decimal=Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("invalid OI decimal") from exc
        if not decimal.is_finite() or decimal<0:
            raise ValueError("invalid OI quantity")
        parsed.append({"symbol":symbol,"timestamp_ms":ts,"open_interest":str(decimal)})
    parsed.sort(key=lambda x:x["timestamp_ms"])
    return parsed


async def fetch_funding_page(base_url,symbol,start_ms=None,end_ms=None,limit=200):
    """One bounded public funding-history page; no trading or database writes.

    Reuses Grid's existing Bybit transport and refuses malformed records before
    returning any observations. A page never attests completeness, gap coverage
    or authenticated source receipts; those belong to the versioned read API.
    """
    from decimal import Decimal,InvalidOperation
    from .bybit import _bounded_int,_https_origin,_read_bounded_http_response,_bounded_result

    origin=_https_origin(base_url)
    if (type(symbol) is not str or not 1<=len(symbol)<=64 or
            not symbol.isascii() or not symbol.isalnum()):
        raise ValueError("invalid funding symbol")
    _bounded_int(limit,"funding history page limit",1,200)
    if start_ms is not None:
        _bounded_int(start_ms,"funding start_ms",0,2**63-1)
    if end_ms is not None:
        _bounded_int(end_ms,"funding end_ms",0,2**63-1)
    if start_ms is not None and end_ms is not None and end_ms<start_ms:
        raise ValueError("invalid funding time range")
    params={"category":"linear","symbol":symbol,"limit":limit}
    if start_ms is not None:
        params["startTime"]=start_ms
    if end_ms is not None:
        params["endTime"]=end_ms
    timeout=aiohttp.ClientTimeout(total=30,connect=10,sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout,trust_env=False,auto_decompress=False,
                                    cookie_jar=aiohttp.DummyCookieJar(),
                                    headers={"Accept-Encoding":"identity"}) as session:
        async with session.get(origin+"/v5/market/funding/history",
                               params=params,allow_redirects=False) as response:
            raw=await _read_bounded_http_response(response)
    rows=_bounded_result(raw)["list"]
    if len(rows)>limit:
        raise ValueError("funding history page exceeds request limit")
    parsed=[]
    timestamps=set()
    for row in rows:
        if type(row) is not dict or row.get("symbol")!=symbol:
            raise ValueError("invalid funding instrument identity")
        stamp=row.get("fundingRateTimestamp")
        if type(stamp) is str and 1<=len(stamp)<=19 and stamp.isascii() and stamp.isdecimal():
            stamp=int(stamp)
        if type(stamp) is not int or not 0<stamp<=2**63-1 or stamp in timestamps:
            raise ValueError("invalid or duplicate funding timestamp")
        rate=row.get("fundingRate")
        if type(rate) is not str or not 1<=len(rate)<=80:
            raise ValueError("invalid funding rate representation")
        try:
            exact=Decimal(rate)
        except InvalidOperation as exc:
            raise ValueError("invalid funding decimal") from exc
        if not exact.is_finite():
            raise ValueError("nonfinite funding rate")
        timestamps.add(stamp)
        parsed.append({"symbol":symbol,"timestamp_ms":stamp,"funding_rate":str(exact)})
    parsed.sort(key=lambda item:item["timestamp_ms"])
    return parsed


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
        # A short Bybit page is not evidence of history exhaustion.
        # Advance the cursor and resume until an empty page, launch bound or page budget.
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

async def recover_stale_backfill_jobs(pool,stale_minutes=30,max_attempts=5):
    """Requeue abandoned claims without assuming any history was completed.

    The caller owns the dedicated Grid pool. This only changes stale Grid
    scheduler metadata; OHLCV records and other databases remain untouched.
    """
    if type(stale_minutes) is not int or not 1<=stale_minutes<=1440:
        raise ValueError("invalid stale backfill window")
    if type(max_attempts) is not int or not 1<=max_attempts<=100:
        raise ValueError("invalid backfill attempt cap")
    return await pool.execute("""UPDATE market_backfill_state SET
      status=CASE WHEN attempts<$2 THEN 'retry' ELSE 'failed' END,
      last_error=COALESCE(last_error,'recovered stale backfill worker'),
      updated_at=now()
      WHERE status='running' AND updated_at<now()-($1*interval '1 minute')""",
      stale_minutes,max_attempts)


async def run_backfill_worker(pool,base_url,stop_event=None,max_pages=50):
    from .data_capabilities import set_capability
    stop_event=stop_event or asyncio.Event();done=chunks=failed=0
    if not stop_event.is_set():
        await recover_stale_backfill_jobs(pool)
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
