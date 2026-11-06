import asyncio, logging
log=logging.getLogger("instrument_lifecycle")

async def ensure_instrument_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS instruments(
          symbol text PRIMARY KEY,
          contract_type text,
          status text NOT NULL,
          tick_size numeric,
          first_seen timestamptz NOT NULL DEFAULT now(),
          last_seen timestamptz NOT NULL DEFAULT now(),
          retired_at timestamptz,
          missing_since timestamptz,
          missing_confirmations integer NOT NULL DEFAULT 0,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        ALTER TABLE instruments ADD COLUMN IF NOT EXISTS missing_since timestamptz;
        ALTER TABLE instruments ADD COLUMN IF NOT EXISTS missing_confirmations integer NOT NULL DEFAULT 0;
        """)

async def reconcile_instruments(pool,current,*,retire_confirmations=3):
    """Reconcile a successful complete discovery snapshot.

    Missing once is not delisting. A symbol is retired only after repeated
    successful snapshots omit it; historical data is retained.
    """
    current_map={x["symbol"]:x for x in current}
    async with pool.acquire() as c:
        rows=await c.fetch("SELECT symbol,status FROM instruments")
        known={r["symbol"]:r["status"] for r in rows}
        added=[]
        for sym,x in current_map.items():
            if sym not in known: added.append(sym)
            await c.execute("""INSERT INTO instruments(symbol,contract_type,status,tick_size,metadata)
              VALUES($1,$2,'Trading',$3,$4::jsonb)
              ON CONFLICT(symbol) DO UPDATE SET
                contract_type=EXCLUDED.contract_type,status='Trading',tick_size=EXCLUDED.tick_size,
                last_seen=now(),retired_at=NULL,missing_since=NULL,missing_confirmations=0,
                metadata=EXCLUDED.metadata""",
                sym,x.get("contract_type"),x.get("tick_size"),__import__("json").dumps(x))
        missing=[sym for sym,status in known.items() if status=="Trading" and sym not in current_map]
        retired=[]
        for sym in missing:
            row=await c.fetchrow("""UPDATE instruments SET
              missing_since=COALESCE(missing_since,now()),
              missing_confirmations=missing_confirmations+1
              WHERE symbol=$1 AND status='Trading'
              RETURNING missing_confirmations""",sym)
            if row and int(row["missing_confirmations"])>=max(1,int(retire_confirmations)):
                await c.execute("""UPDATE instruments SET status='Retired',retired_at=now()
                  WHERE symbol=$1 AND status='Trading'""",sym)
                retired.append(sym)
                # A reboot must not resurrect endless historical retries for a delisted symbol.
                try:
                    await c.execute("""UPDATE market_backfill_state SET status='retired',
                      last_error='instrument retired during discovery reconciliation',updated_at=now()
                      WHERE symbol=$1 AND status IN ('queued','retry','running')""",sym)
                except Exception:
                    log.exception("failed to retire symbol backfill",extra={"event":"retired_backfill","symbol":sym})
        return added,retired

async def purge_retired(pool,grace_days=30):
    """Preserve retired history until a separate retention policy is approved.

    Retirement and elapsed grace alone do not authorize deletion. Keep this
    compatibility hook non-destructive, without even acquiring a DB connection.
    """
    return []
