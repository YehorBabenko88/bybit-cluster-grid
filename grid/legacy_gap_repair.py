from __future__ import annotations
import asyncio,aiohttp,sqlite3
from .legacy_gap_scan import MINUTE_MS

REQUIRED=("symbol","ts","open","high","low","close","volume","turnover")

def validate_schema(conn):
    cols={r[1] for r in conn.execute("PRAGMA table_info(candles)")}
    missing=[x for x in REQUIRED if x not in cols]
    if missing:raise RuntimeError("legacy candles schema missing: "+",".join(missing))

async def fetch_range(base_url,symbol,start_ms,end_ms,session=None,pause=.08):
    own=session is None
    session=session or aiohttp.ClientSession()
    out=[];cursor=int(end_ms)
    try:
        while cursor>=int(start_ms):
            params={"category":"linear","symbol":symbol,"interval":"1","start":int(start_ms),
                    "end":cursor,"limit":1000}
            async with session.get(base_url+"/v5/market/kline",params=params,timeout=30) as r:
                r.raise_for_status();j=await r.json()
            if j.get("retCode")!=0:raise RuntimeError(j.get("retMsg") or "Bybit kline error")
            rows=j.get("result",{}).get("list",[])
            if not rows:break
            rows=sorted(rows,key=lambda x:int(x[0]))
            out.extend(x for x in rows if int(start_ms)<=int(x[0])<=int(end_ms))
            oldest=min(int(x[0]) for x in rows)
            if oldest<=int(start_ms):break
            nxt=oldest-MINUTE_MS
            if nxt>=cursor:raise RuntimeError(f"legacy repair paging stalled {symbol}")
            cursor=nxt
            await asyncio.sleep(pause)
    finally:
        if own:await session.close()
    dedup={int(x[0]):x for x in out}
    return [dedup[k] for k in sorted(dedup)]

def merge_rows(conn,symbol,rows):
    validate_schema(conn);inserted=0
    with conn:
        for r in rows:
            ts=int(r[0])
            old=conn.execute("""SELECT open,high,low,close,volume,turnover FROM candles
              WHERE symbol=? AND ts=?""",(symbol,ts)).fetchone()
            vals=tuple(r[i] for i in range(1,7))
            if old is not None:
                if tuple(str(x) for x in old)!=tuple(str(x) for x in vals):
                    raise RuntimeError(f"LEGACY_OHLCV_CONFLICT {symbol} {ts}")
                continue
            conn.execute("""INSERT INTO candles(symbol,ts,open,high,low,close,volume,turnover)
              VALUES(?,?,?,?,?,?,?,?)""",(symbol,ts,*vals));inserted+=1
    return inserted

async def repair_gaps(conn,base_url,gaps,pause_flag=None):
    inserted=0
    async with aiohttp.ClientSession() as session:
        for g in gaps:
            while pause_flag and __import__("os").path.exists(pause_flag):await asyncio.sleep(2)
            rows=await fetch_range(base_url,g.symbol,g.start_ms,g.end_ms,session=session)
            inserted+=merge_rows(conn,g.symbol,rows)
    return inserted
