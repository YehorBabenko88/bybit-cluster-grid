from __future__ import annotations
import asyncio,hashlib,json,os,sqlite3,tempfile,uuid
from datetime import datetime,timezone
from pathlib import Path
from .compute_artifacts import publish_compute_artifact
from .config import settings

FORMAT_VERSION="strattester-sqlite-v1"
SCHEMA_SQL="""
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candles (
 symbol TEXT NOT NULL,timeframe TEXT NOT NULL,open_time INTEGER NOT NULL,
 open REAL NOT NULL,high REAL NOT NULL,low REAL NOT NULL,close REAL NOT NULL,
 volume REAL NOT NULL,turnover REAL,complete INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(symbol,timeframe,open_time));
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol,timeframe,open_time);
"""


def _as_utc(value):
    if isinstance(value,datetime):
        dt=value
    else:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ms(dt):
    return int(round(dt.timestamp()*1000))


def _build_sqlite(path,rows):
    con=sqlite3.connect(path)
    try:
        con.executescript(SCHEMA_SQL)
        con.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('schema_version','2')")
        con.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('dataset_format',?)",(FORMAT_VERSION,))
        con.executemany("""INSERT INTO candles
          (symbol,timeframe,open_time,open,high,low,close,volume,turnover,complete)
          VALUES(?,?,?,?,?,?,?,?,?,1)""",rows)
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


async def export_market_dataset(pool,*,symbols,start_ts,end_ts,owner="control",max_rows=None):
    symbols=tuple(sorted({str(x).strip().upper() for x in symbols if str(x).strip()}))
    if not symbols:raise ValueError("dataset export requires symbols")
    start=_as_utc(start_ts);end=_as_utc(end_ts)
    if end<start:raise ValueError("dataset export end precedes start")
    start_ms=((_ms(start)+59_999)//60_000)*60_000
    end_ms=(_ms(end)//60_000)*60_000
    if end_ms<start_ms:raise ValueError("dataset export window contains no complete minute")
    max_rows=int(max_rows or getattr(settings,"research_dataset_export_max_rows",500_000))
    expected_per=((end_ms-start_ms)//60_000)+1
    expected_total=expected_per*len(symbols)
    if expected_total>max_rows:
        raise ValueError(f"dataset export requires {expected_total} rows; limit is {max_rows}")
    start_aligned=datetime.fromtimestamp(start_ms/1000,tz=timezone.utc)
    end_aligned=datetime.fromtimestamp(end_ms/1000,tz=timezone.utc)
    rows=await pool.fetch("""SELECT symbol,ts,open,high,low,close,
      COALESCE(buy_volume,0) buy_volume,COALESCE(sell_volume,0) sell_volume,
      (COALESCE(buy_volume,0)+COALESCE(sell_volume,0)) volume
      FROM candles_1m WHERE symbol=ANY($1::text[]) AND ts>=$2 AND ts<=$3
      ORDER BY symbol,ts""",list(symbols),start_aligned,end_aligned)
    source="trade_archive"
    if len(rows)!=expected_total:
        # Cold start must not wait for the much larger public-trade archive when
        # complete Bybit REST OHLCV is already available.  Core Strattester
        # research can use OHLCV; footprint-dependent research still requires
        # the trade-archive capability separately.
        rows=await pool.fetch("""SELECT symbol,ts,open,high,low,close,
          0::numeric buy_volume,0::numeric sell_volume,volume
          FROM ohlcv_1m WHERE symbol=ANY($1::text[]) AND ts>=$2 AND ts<=$3
          ORDER BY symbol,ts""",list(symbols),start_aligned,end_aligned)
        source="bybit_rest_ohlcv"
    if len(rows)!=expected_total:
        raise ValueError(f"dataset history incomplete: expected {expected_total} rows, got {len(rows)}")
    last={};counts={s:0 for s in symbols};sqlite_rows=[];h=hashlib.sha256()
    for r in rows:
        symbol=str(r["symbol"]);ts=_ms(_as_utc(r["ts"]))
        if symbol not in counts:raise ValueError("dataset query returned unexpected symbol")
        prev=last.get(symbol)
        if prev is None and ts!=start_ms:
            raise ValueError(f"dataset {symbol} does not start at requested minute")
        if prev is not None and ts-prev!=60_000:
            raise ValueError(f"dataset {symbol} contains a minute gap")
        last[symbol]=ts;counts[symbol]+=1
        o,hv,l,c=(float(r["open"]),float(r["high"]),float(r["low"]),float(r["close"]))
        buy=float(r["buy_volume"]);sell=float(r["sell_volume"]);volume=float(r["volume"])
        semantic={"source":source,"symbol":symbol,"ts":ts,"open":str(r["open"]),"high":str(r["high"]),
                  "low":str(r["low"]),"close":str(r["close"]),"volume":str(r["volume"]),
                  "buy_volume":str(r["buy_volume"]),"sell_volume":str(r["sell_volume"])}
        h.update(json.dumps(semantic,sort_keys=True,separators=(",",":")).encode("utf-8"));h.update(b"\n")
        sqlite_rows.append((symbol,"1m",ts,o,hv,l,c,volume,None))
    for symbol in symbols:
        if counts[symbol]!=expected_per or last.get(symbol)!=end_ms:
            raise ValueError(f"dataset {symbol} is incomplete")
    dataset_hash=h.hexdigest();dataset_id=uuid.uuid4()
    criteria={"symbols":list(symbols),"start_ts":start_aligned.isoformat(),
              "end_ts":end_aligned.isoformat(),"format":FORMAT_VERSION,"source":source}
    await pool.execute("""INSERT INTO dataset_snapshots
      (id,purpose,cutoff_ts,created_by,criteria,status,dataset_hash,sample_count,feature_version)
      VALUES($1,'strattester_market_history',$2,$3,$4::jsonb,'BUILDING',$5,$6,$7)""",
      dataset_id,end_aligned,str(owner),json.dumps(criteria),dataset_hash,len(sqlite_rows),FORMAT_VERSION)
    root=Path(settings.content_cache_root);root.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="grid-market-dataset-",suffix=".db",dir=root);os.close(fd)
    try:
        await asyncio.to_thread(_build_sqlite,tmp,sqlite_rows)
        artifact=await publish_compute_artifact(pool,tmp,artifact_type="research_dataset",
            metadata={"dataset_id":str(dataset_id),"dataset_hash":dataset_hash,**criteria},reusable=True)
        await pool.execute("""UPDATE dataset_snapshots SET status='READY',artifact_id=$2
          WHERE id=$1 AND status='BUILDING'""",dataset_id,uuid.UUID(str(artifact["id"])))
        return {"id":str(dataset_id),"dataset_hash":dataset_hash,
                "artifact_id":str(artifact["id"]),"artifact_sha256":artifact["sha256"],
                "sample_count":len(sqlite_rows),"criteria":criteria}
    except Exception:
        await pool.execute("UPDATE dataset_snapshots SET status='FAILED' WHERE id=$1",dataset_id)
        raise
    finally:
        try:os.remove(tmp)
        except FileNotFoundError:pass
