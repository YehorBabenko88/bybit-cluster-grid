from __future__ import annotations
import os,shutil,sqlite3
from pathlib import Path
from .legacy_gap_repair import REQUIRED

def preflight(path,min_free_gb=10):
    p=Path(path)
    if not p.exists():raise FileNotFoundError(p)
    free=shutil.disk_usage(p.parent).free
    conn=sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro",uri=True)
    try:
        check=conn.execute("PRAGMA quick_check").fetchone()[0]
        if str(check).lower()!="ok":raise RuntimeError(f"SQLite quick_check failed: {check}")
        cols={r[1] for r in conn.execute("PRAGMA table_info(candles)")}
        missing=[x for x in REQUIRED if x not in cols]
        if missing:raise RuntimeError("legacy candles schema missing: "+",".join(missing))
        lo,hi,count=conn.execute("SELECT MIN(ts),MAX(ts),COUNT(*) FROM candles").fetchone()
        if count and (int(hi)<1_000_000_000_000 or int(hi)>10_000_000_000_000):
            raise RuntimeError("legacy ts is not plausible epoch milliseconds")
        dup=conn.execute("""SELECT symbol,ts,count(*) n FROM candles
          GROUP BY symbol,ts HAVING count(*)>1 LIMIT 1""").fetchone()
        if dup:raise RuntimeError(f"duplicate legacy candle {dup[0]} {dup[1]}")
        indexes=list(conn.execute("PRAGMA index_list(candles)"))
        return {"ok":True,"bytes":p.stat().st_size,"free_bytes":free,"rows":int(count or 0),
                "min_ts":lo,"max_ts":hi,"indexes":len(indexes),
                "copy_recommended":free>p.stat().st_size+int(min_free_gb*1024**3)}
    finally:conn.close()
