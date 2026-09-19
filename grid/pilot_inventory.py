from __future__ import annotations
import hashlib,json,sqlite3
from pathlib import Path
from .legacy_gap_scan import scan_symbol,append_tail_gap,coverage_fingerprint

def list_symbols(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM candles ORDER BY symbol")]

def inventory(source_path,cutoff_ms):
    p=Path(source_path)
    conn=sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro",uri=True)
    try:
        symbols=list_symbols(conn);coverage=[];all_gaps=[]
        for symbol in symbols:
            s=append_tail_gap(scan_symbol(conn,symbol,cutoff_ms),cutoff_ms)
            coverage.append({"symbol":symbol,"min_ts":s["min_ts"],"max_ts":s["max_ts"],
                             "candles":s["candles"],"gap_minutes":s["gap_minutes"],
                             "coverage_fingerprint":coverage_fingerprint(s)})
            all_gaps.extend(s["gaps"])
        return {"symbols":len(symbols),"coverage":coverage,"gaps":all_gaps,
                "gap_minutes":sum(g.missing_minutes for g in all_gaps)}
    finally:conn.close()

def verified_inventory(source_path,cutoff_ms):
    x=inventory(source_path,cutoff_ms)
    bad=[r for r in x["coverage"] if r["gap_minutes"]]
    if bad:raise RuntimeError(f"LEGACY_REPAIR_INCOMPLETE symbols={len(bad)} missing_minutes={sum(r['gap_minutes'] for r in bad)}")
    return x
