from __future__ import annotations
import argparse,asyncio,hashlib,json,os,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from .service import prepare_database,bootstrap_logging
from .data_capabilities import set_capability

def _dt_ms(ms):
    return datetime.fromtimestamp(int(ms)/1000.0,timezone.utc) if ms is not None else None

def _source_id(handoff):
    p=Path(handoff["source_candle_db"])
    st=p.stat()
    payload={"path":str(p.resolve()),"size":st.st_size,"mtime_ns":st.st_mtime_ns,
             "cutoff":handoff.get("research_cutoff_ms"),"coverage":handoff.get("coverage_fingerprints",{})}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _open_ro(path):
    return sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro",uri=True)

async def _ensure_import_row(pool,source_id,handoff):
    await pool.execute("""INSERT INTO legacy_bootstrap_imports
      (source_id,source_path,research_path,research_cutoff,status,manifest)
      VALUES($1,$2,$3,$4,'IMPORTING',$5::jsonb)
      ON CONFLICT(source_id) DO UPDATE SET status=CASE
        WHEN legacy_bootstrap_imports.status='VERIFIED' THEN 'VERIFIED' ELSE 'IMPORTING' END,
        manifest=EXCLUDED.manifest,last_error=NULL""",
      source_id,handoff["source_candle_db"],handoff.get("research_db"),
      _dt_ms(handoff.get("research_cutoff_ms")),json.dumps(handoff))

async def _prepare_stage(conn):
    await conn.execute("""CREATE TEMP TABLE IF NOT EXISTS legacy_ohlcv_stage(
      symbol text,ts timestamptz,open numeric,high numeric,low numeric,close numeric,volume numeric,turnover numeric)
      ON COMMIT PRESERVE ROWS""")

async def _merge_batch(conn,records):
    if not records:return 0
    await conn.execute("TRUNCATE legacy_ohlcv_stage")
    await conn.copy_records_to_table("legacy_ohlcv_stage",
      records=records,columns=("symbol","ts","open","high","low","close","volume","turnover"))
    bad=await conn.fetchrow("""SELECT s.symbol,s.ts FROM legacy_ohlcv_stage s JOIN ohlcv_1m o
      ON o.symbol=s.symbol AND o.ts=s.ts
      WHERE o.open IS DISTINCT FROM s.open OR o.high IS DISTINCT FROM s.high
         OR o.low IS DISTINCT FROM s.low OR o.close IS DISTINCT FROM s.close
         OR o.volume IS DISTINCT FROM s.volume OR o.turnover IS DISTINCT FROM s.turnover LIMIT 1""")
    if bad:raise RuntimeError(f"OHLCV_DATA_CONFLICT {bad['symbol']} {bad['ts']}")
    r=await conn.execute("""INSERT INTO ohlcv_1m(symbol,ts,open,high,low,close,volume,turnover,source)
      SELECT symbol,ts,open,high,low,close,volume,turnover,'LEGACY_SQLITE'
      FROM legacy_ohlcv_stage ON CONFLICT(symbol,ts) DO NOTHING""")
    return int(r.split()[-1]) if r else 0

async def import_symbol(pool,src,source_id,row,cutoff_ms,batch_size=5000):
    symbol=row["symbol"]; expected_fp=row.get("coverage_fingerprint") or ""
    existing=await pool.fetchrow("""SELECT status,coverage_fingerprint,imported_candles
      FROM legacy_symbol_coverage WHERE source_id=$1 AND symbol=$2""",source_id,symbol)
    if existing and existing["status"]=="VERIFIED" and existing["coverage_fingerprint"]==expected_fp:
        return {"symbol":symbol,"status":"skipped_verified","candles":existing["imported_candles"]}

    lo,hi,count=src.execute("""SELECT MIN(ts),MAX(ts),COUNT(*) FROM candles
      WHERE symbol=? AND ts<=?""",(symbol,int(cutoff_ms))).fetchone()
    expected=int(row.get("candles") or count)
    if int(count)!=expected:
        raise RuntimeError(f"LEGACY_COVERAGE_MISMATCH {symbol}: handoff={expected} sqlite={count}")
    inserted=0
    async with pool.acquire() as c:
        await _prepare_stage(c)
        cur=src.execute("""SELECT ts,open,high,low,close,volume,turnover FROM candles
          WHERE symbol=? AND ts<=? ORDER BY ts""",(symbol,int(cutoff_ms)))
        while True:
            rows=cur.fetchmany(int(batch_size))
            if not rows:break
            rec=[(symbol,_dt_ms(r[0]),r[1],r[2],r[3],r[4],r[5],r[6]) for r in rows]
            async with c.transaction():
                inserted+=await _merge_batch(c,rec)
        db_count=await c.fetchval("""SELECT count(*) FROM ohlcv_1m
          WHERE symbol=$1 AND ts>=$2 AND ts<=$3""",symbol,_dt_ms(lo),_dt_ms(hi))
        if int(db_count)<int(count):
            raise RuntimeError(f"GRID_COVERAGE_VERIFY_FAILED {symbol}: grid={db_count} source={count}")
        await c.execute("""INSERT INTO legacy_symbol_coverage
          (source_id,symbol,min_ts,max_ts,candles,gap_minutes,coverage_fingerprint,status,imported_candles,verified_at,last_error)
          VALUES($1,$2,$3,$4,$5,$6,$7,'VERIFIED',$5,now(),NULL)
          ON CONFLICT(source_id,symbol) DO UPDATE SET min_ts=EXCLUDED.min_ts,max_ts=EXCLUDED.max_ts,
          candles=EXCLUDED.candles,gap_minutes=EXCLUDED.gap_minutes,
          coverage_fingerprint=EXCLUDED.coverage_fingerprint,status='VERIFIED',
          imported_candles=EXCLUDED.imported_candles,verified_at=now(),last_error=NULL""",
          source_id,symbol,_dt_ms(lo),_dt_ms(hi),int(count),int(row.get("gap_minutes") or 0),expected_fp)
        await c.execute("""INSERT INTO market_backfill_state(symbol,timeframe,status,oldest_loaded_ts,newest_loaded_ts)
          VALUES($1,'1',$2,$3,$4)
          ON CONFLICT(symbol,timeframe) DO UPDATE SET status=EXCLUDED.status,
          oldest_loaded_ts=LEAST(COALESCE(market_backfill_state.oldest_loaded_ts,EXCLUDED.oldest_loaded_ts),EXCLUDED.oldest_loaded_ts),
          newest_loaded_ts=GREATEST(COALESCE(market_backfill_state.newest_loaded_ts,EXCLUDED.newest_loaded_ts),EXCLUDED.newest_loaded_ts),
          updated_at=now()""",symbol,"done" if int(row.get("gap_minutes") or 0)==0 else "partial",_dt_ms(lo),_dt_ms(hi))
    await set_capability(pool,symbol,"ohlcv_history","READY" if int(row.get("gap_minutes") or 0)==0 else "PARTIAL",
                         {"source":"legacy_sqlite","source_id":source_id,"cutoff_ms":cutoff_ms})
    return {"symbol":symbol,"status":"verified","candles":count,"inserted":inserted}

async def import_research(pool,research_path,source_id):
    if not research_path or not os.path.exists(research_path):return {"levels":0,"samples":0}
    rdb=_open_ro(research_path); levels=samples=0
    try:
        cols={x[1] for x in rdb.execute("PRAGMA table_info(legacy_levels)")}
        if cols:
            for rows in iter(lambda:rdb.execute("""SELECT symbol,timeframe,level_type,source_start,available_at,
              price,trigger,broken,broken_at,entries FROM legacy_levels""").fetchmany(0),[]): pass
            cur=rdb.execute("""SELECT symbol,timeframe,level_type,source_start,available_at,
              price,trigger,broken,broken_at,entries FROM legacy_levels""")
            while True:
                batch=cur.fetchmany(5000)
                if not batch:break
                async with pool.acquire() as c:
                    async with c.transaction():
                        for x in batch:
                            await c.execute("""INSERT INTO imported_historical_levels
                              (source_id,symbol,timeframe,level_type,source_start,available_at,price,trigger,broken,broken_at,entries)
                              VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT DO NOTHING""",
                              source_id,x[0],x[1],x[2],_dt_ms(x[3]),_dt_ms(x[4]),x[5],x[6],bool(x[7]),_dt_ms(x[8]),x[9])
                            await c.execute("""INSERT INTO historical_levels
                              (symbol,timeframe,level_kind,source_ts,price,active,first_cross_ts,test_count,available_ts)
                              VALUES($1,$2,$3,$4,$5,$6,$7,0,$8)
                              ON CONFLICT(symbol,timeframe,level_kind,source_ts) DO UPDATE SET
                              price=EXCLUDED.price,active=EXCLUDED.active,
                              first_cross_ts=COALESCE(historical_levels.first_cross_ts,EXCLUDED.first_cross_ts),
                              available_ts=EXCLUDED.available_ts""",
                              x[0],x[1],x[2],_dt_ms(x[3]),x[5],not bool(x[7]),_dt_ms(x[8]),_dt_ms(x[4]))
                            levels+=1
        if {x[1] for x in rdb.execute("PRAGMA table_info(research_trades)")}:
            cur=rdb.execute("""SELECT symbol,strategy,family,direction,signal_ts,entry_ts,exit_ts,entry_price,
              exit_price,stop_loss,take_profit,horizon_minutes,split,exit_reason,gross_pnl_pct,net_pnl_pct,
              mfe_pct,mae_pct,features_json FROM research_trades""")
            while True:
                batch=cur.fetchmany(5000)
                if not batch:break
                async with pool.acquire() as c:
                    async with c.transaction():
                        for x in batch:
                            payload={"strategy":x[1],"family":x[2],"direction":x[3],"entry_ts":x[5],"exit_ts":x[6],
                              "entry_price":x[7],"exit_price":x[8],"stop_loss":x[9],"take_profit":x[10],
                              "horizon_minutes":x[11],"exit_reason":x[13],"gross_pnl_pct":x[14],
                              "net_pnl_pct":x[15],"mfe_pct":x[16],"mae_pct":x[17],
                              "features":json.loads(x[18] or "{}")}
                            key=hashlib.sha256(f"trade:{x[0]}:{x[1]}:{x[4]}:{x[5]}".encode()).hexdigest()
                            await c.execute("""INSERT INTO legacy_research_samples
                              (source_id,symbol,sample_key,sample_type,event_ts,split,payload)
                              VALUES($1,$2,$3,'ADVANCED_TRADE',$4,$5,$6::jsonb) ON CONFLICT DO NOTHING""",
                              source_id,x[0],key,_dt_ms(x[4]),x[12],json.dumps(payload))
                            samples+=1
        if {x[1] for x in rdb.execute("PRAGMA table_info(research_level_events)")}:
            cur=rdb.execute("""SELECT symbol,timeframe,level_type,source_start,break_time,payload_json
              FROM research_level_events""")
            while True:
                batch=cur.fetchmany(5000)
                if not batch:break
                async with pool.acquire() as c:
                    async with c.transaction():
                        for x in batch:
                            key=hashlib.sha256(f"level:{x[0]}:{x[1]}:{x[2]}:{x[3]}:{x[4]}".encode()).hexdigest()
                            await c.execute("""INSERT INTO legacy_research_samples
                              (source_id,symbol,sample_key,sample_type,event_ts,split,payload)
                              VALUES($1,$2,$3,'LEVEL_EVENT',$4,NULL,$5::jsonb) ON CONFLICT DO NOTHING""",
                              source_id,x[0],key,_dt_ms(x[4]),x[5])
                            samples+=1
    finally:rdb.close()
    return {"levels":levels,"samples":samples}

async def import_handoff(pool,handoff_path,batch_size=5000):
    handoff=json.loads(Path(handoff_path).read_text(encoding="utf-8"))
    if handoff.get("phase")!="GRID_IMPORT_PENDING":raise ValueError("handoff is not GRID_IMPORT_PENDING")
    if not handoff.get("cache_repair_complete"):raise ValueError("legacy cache repair is not complete")
    cutoff=int(handoff["research_cutoff_ms"]);source_id=_source_id(handoff)
    await _ensure_import_row(pool,source_id,handoff)
    src=_open_ro(handoff["source_candle_db"]); imported=0
    try:
        cov={x["symbol"]:x for x in handoff.get("coverage",[])}
        fps=handoff.get("coverage_fingerprints") or {}
        for symbol,row in cov.items():
            row=dict(row);row["coverage_fingerprint"]=fps.get(symbol,"")
            result=await import_symbol(pool,src,source_id,row,cutoff,batch_size=batch_size)
            imported+=int(result.get("candles") or 0)
    except Exception as exc:
        await pool.execute("UPDATE legacy_bootstrap_imports SET status='FAILED',last_error=$2 WHERE source_id=$1",source_id,str(exc)[:4000])
        raise
    finally:src.close()
    research=await import_research(pool,handoff.get("research_db"),source_id)
    verified=await pool.fetchval("""SELECT count(*) FROM legacy_symbol_coverage
      WHERE source_id=$1 AND status='VERIFIED'""",source_id)
    expected=len(handoff.get("coverage",[]))
    if int(verified)!=expected:raise RuntimeError(f"legacy import incomplete: {verified}/{expected}")
    await pool.execute("""UPDATE legacy_bootstrap_imports SET status='VERIFIED',coverage_symbols=$2,
      imported_candles=$3,imported_levels=$4,imported_samples=$5,verified_at=now(),last_error=NULL
      WHERE source_id=$1""",source_id,expected,imported,research["levels"],research["samples"])
    marker=Path(handoff_path).with_name("grid_import_verified.json")
    marker.write_text(json.dumps({"source_id":source_id,"status":"VERIFIED","coverage_symbols":expected,
      "levels":research["levels"],"samples":research["samples"]},indent=2),encoding="utf-8")
    return {"source_id":source_id,"coverage_symbols":expected,"levels":research["levels"],"samples":research["samples"]}

async def _amain(args):
    db=await prepare_database()
    try:return await import_handoff(db.pool,args.handoff,args.batch_size)
    finally:await db.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--handoff",required=True)
    p.add_argument("--batch-size",type=int,default=5000)
    args=p.parse_args();bootstrap_logging()
    print(json.dumps(asyncio.run(_amain(args)),indent=2,default=str))

if __name__=="__main__":main()
