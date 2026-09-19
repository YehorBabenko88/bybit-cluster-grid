import json
from datetime import datetime,timezone
from .archive_discovery import list_symbol_archives,fallback_probe,archive_url
from .data_capabilities import set_capability

async def seed_discovery(pool,symbols):
    async with pool.acquire() as c:
        async with c.transaction():
            for item in symbols:
                symbol=item["symbol"] if isinstance(item,dict) else str(item)
                await c.execute("""INSERT INTO trade_archive_discovery(symbol,status)
                  VALUES($1,'queued') ON CONFLICT(symbol) DO NOTHING""",symbol)

async def claim_discovery(pool):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM trade_archive_discovery
              WHERE status IN ('queued','retry') ORDER BY COALESCE(last_scan_at,'epoch'::timestamptz),symbol
              FOR UPDATE SKIP LOCKED LIMIT 1""")
            if not row:return None
            await c.execute("""UPDATE trade_archive_discovery SET status='running',
              last_scan_at=now(),last_error=NULL WHERE symbol=$1""",row["symbol"])
            return dict(row)

async def scan_symbol(pool,base_url,symbol,probe_days=30):
    try:
        result=await list_symbol_archives(base_url,symbol)
        if not result["dates"]:
            result=await fallback_probe(base_url,symbol,probe_days)
        today=datetime.now(timezone.utc).date()
        dates=sorted(d for d in result["dates"] if d<today)
        async with pool.acquire() as c:
            async with c.transaction():
                for d in dates:
                    url=(result.get("urls") or {}).get(d) or archive_url(base_url,symbol,d)
                    await c.execute("""INSERT INTO trade_archive_backfill
                      (symbol,archive_date,status,source_uri) VALUES($1,$2,'queued',$3)
                      ON CONFLICT(symbol,archive_date) DO UPDATE SET
                        source_uri=EXCLUDED.source_uri,
                        status=CASE WHEN trade_archive_backfill.status IN ('done','running')
                          THEN trade_archive_backfill.status ELSE 'queued' END""",symbol,d,url)
                await c.execute("""UPDATE trade_archive_discovery SET status=$2,mode=$3,
                  earliest_date=$4,latest_date=$5,discovered_files=$6,last_scan_at=now(),
                  last_error=NULL,details=$7::jsonb WHERE symbol=$1""",
                  symbol,"done" if dates else "unavailable",result["mode"],
                  dates[0] if dates else None,dates[-1] if dates else None,len(dates),
                  json.dumps({"remote_status":result["status"]}))
        if dates:
            await set_capability(pool,symbol,"trade_history","QUEUED",
                                 {"discovered_files":len(dates),"discovery_mode":result["mode"]})
        else:
            await set_capability(pool,symbol,"trade_history","UNAVAILABLE",
                                 {"discovery_mode":result["mode"]})
        return {"symbol":symbol,"files":len(dates),"mode":result["mode"]}
    except Exception as exc:
        await pool.execute("""UPDATE trade_archive_discovery SET status='retry',
          last_error=$2,last_scan_at=now() WHERE symbol=$1""",symbol,str(exc)[:4000])
        raise
