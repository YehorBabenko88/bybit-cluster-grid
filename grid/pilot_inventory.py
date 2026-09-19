from __future__ import annotations
import hashlib,json,sqlite3
from pathlib import Path
from .legacy_gap_scan import scan_symbol,append_tail_gap,coverage_fingerprint

def list_symbols(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM candles ORDER BY symbol")]

def inventory(source_path,cutoff_ms,lifecycle=None):
    p=Path(source_path)
    conn=sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro",uri=True)
    try:
        symbols=list_symbols(conn);coverage=[];all_gaps=[]
        for symbol in symbols:
            meta=(lifecycle or {}).get(symbol,{})
            scan=scan_symbol(conn,symbol,cutoff_ms)
            status=str(meta.get("status","")).upper()
            end_ms=meta.get("end_time_ms") or meta.get("delivery_time_ms")
            if status in ("TRADING","ACTIVE"):
                target=int(cutoff_ms)
            elif end_ms:
                target=min(int(cutoff_ms),int(end_ms))
            elif lifecycle is None:
                target=int(cutoff_ms)
            else:
                target=scan["max_ts"]
                scan["lifecycle_unknown"]=True
            s=append_tail_gap(scan,target)
            coverage.append({"symbol":symbol,"min_ts":s["min_ts"],"max_ts":s["max_ts"],
                             "candles":s["candles"],"gap_minutes":s["gap_minutes"],
                             "coverage_fingerprint":coverage_fingerprint(s)})
            all_gaps.extend(s["gaps"])
        return {"symbols":len(symbols),"coverage":coverage,"gaps":all_gaps,
                "gap_minutes":sum(g.missing_minutes for g in all_gaps)}
    finally:conn.close()

def verified_inventory(source_path,cutoff_ms,lifecycle=None):
    x=inventory(source_path,cutoff_ms,lifecycle)
    bad=[r for r in x["coverage"] if r["gap_minutes"]]
    if bad:raise RuntimeError(f"LEGACY_REPAIR_INCOMPLETE symbols={len(bad)} missing_minutes={sum(r['gap_minutes'] for r in bad)}")
    return x
