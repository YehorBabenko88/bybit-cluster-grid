from __future__ import annotations
import sqlite3
from dataclasses import dataclass

MINUTE_MS=60_000

@dataclass(frozen=True)
class Gap:
    symbol:str
    start_ms:int
    end_ms:int
    missing_minutes:int
    kind:str="INTERNAL"

def scan_symbol(conn:sqlite3.Connection,symbol:str,cutoff_ms:int|None=None):
    where="WHERE symbol=?"+(" AND ts<=?" if cutoff_ms is not None else "")
    args=(symbol,int(cutoff_ms)) if cutoff_ms is not None else (symbol,)
    row=conn.execute(f"SELECT MIN(ts),MAX(ts),COUNT(*) FROM candles {where}",args).fetchone()
    lo,hi,count=row if row else (None,None,0)
    if lo is None:return {"symbol":symbol,"min_ts":None,"max_ts":None,"candles":0,"gaps":[],"gap_minutes":0}
    sql=f"""WITH x AS (
      SELECT ts,LAG(ts) OVER(ORDER BY ts) prev FROM candles {where}
    ) SELECT prev+?,ts-?,((ts-prev)/?)-1 FROM x WHERE prev IS NOT NULL AND ts-prev>? ORDER BY prev"""
    gaps=[Gap(symbol,int(a),int(b),int(n),"INTERNAL") for a,b,n in conn.execute(sql,(*args,MINUTE_MS,MINUTE_MS,MINUTE_MS,MINUTE_MS))]
    return {"symbol":symbol,"min_ts":int(lo),"max_ts":int(hi),"candles":int(count),
            "gaps":gaps,"gap_minutes":sum(g.missing_minutes for g in gaps)}

def append_tail_gap(scan,cutoff_ms:int):
    if scan["max_ts"] is None:return scan
    start=int(scan["max_ts"])+MINUTE_MS;end=int(cutoff_ms)
    gaps=list(scan["gaps"])
    if start<=end:
        gaps.append(Gap(scan["symbol"],start,end,((end-start)//MINUTE_MS)+1,"TAIL"))
    return {**scan,"gaps":gaps,"gap_minutes":sum(g.missing_minutes for g in gaps)}

def coverage_fingerprint(scan):
    import hashlib,json
    payload={"symbol":scan["symbol"],"min_ts":scan["min_ts"],"max_ts":scan["max_ts"],
             "candles":scan["candles"],"gap_minutes":scan["gap_minutes"],
             "gaps":[(g.start_ms,g.end_ms,g.missing_minutes,g.kind) for g in scan["gaps"]]}
    return hashlib.sha256(json.dumps(payload,separators=(",",":"),sort_keys=True).encode()).hexdigest()
