"""Durable causal forward outcomes for scientific research."""
from __future__ import annotations
import json,math,uuid

async def schedule_outcomes(pool,event_id,hypothesis_fingerprint,symbol,event_ts_ms,
                            reference_price,event_type,payload,horizons_s=(1,2,5,10,30,60)):
    px=float(reference_price)
    if px<=0:raise ValueError("reference price must be positive")
    rows=[]
    for h in sorted({int(x) for x in horizons_s if int(x)>0}):
        rows.append((uuid.uuid4(),str(event_id),str(hypothesis_fingerprint),str(symbol),
                     int(event_ts_ms),int(event_ts_ms)+h*1000,h*1000,px,str(event_type),
                     json.dumps(dict(payload or {}),sort_keys=True,separators=(",",":"))))
    if rows:
        await pool.executemany("""INSERT INTO scientific_outcome_requests(
          id,event_id,hypothesis_fingerprint,symbol,event_ts_ms,due_ts_ms,horizon_ms,
          reference_price,event_type,payload)
          VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
          ON CONFLICT(event_id,hypothesis_fingerprint,horizon_ms) DO NOTHING""",rows)
    return len(rows)

async def observe_price(pool,symbol,ts_ms,price):
    """Complete all due labels using a strictly monotonic per-symbol event clock."""
    now=int(ts_ms);px=float(price)
    if px<=0:return []
    async with pool.acquire() as c:
        async with c.transaction():
            old=await c.fetchrow("SELECT last_observed_ts_ms FROM scientific_outcome_clock WHERE symbol=$1 FOR UPDATE",symbol)
            if old and now<=int(old["last_observed_ts_ms"]):
                return []
            await c.execute("""INSERT INTO scientific_outcome_clock(symbol,last_observed_ts_ms)
              VALUES($1,$2) ON CONFLICT(symbol) DO UPDATE SET
              last_observed_ts_ms=EXCLUDED.last_observed_ts_ms,updated_at=now()""",symbol,now)
            rows=await c.fetch("""SELECT id,event_id,hypothesis_fingerprint,event_ts_ms,due_ts_ms,
              horizon_ms,reference_price,event_type,payload FROM scientific_outcome_requests
              WHERE symbol=$1 AND status='PENDING' AND due_ts_ms<=$2
              ORDER BY due_ts_ms,id FOR UPDATE""",symbol,now)
            out=[]
            for r in rows:
                ref=float(r["reference_price"]);lr=math.log(px/ref)
                await c.execute("""UPDATE scientific_outcome_requests SET status='DONE',
                  completed_at=now(),observed_ts_ms=$2,outcome_price=$3,log_return=$4,return_bps=$5
                  WHERE id=$1 AND status='PENDING'""",r["id"],now,px,lr,lr*10000.0)
                out.append({"id":str(r["id"]),"event_id":r["event_id"],
                    "hypothesis_fingerprint":r["hypothesis_fingerprint"],
                    "event_ts_ms":int(r["event_ts_ms"]),"label_ts_ms":now,
                    "horizon_ms":int(r["horizon_ms"]),"reference_price":ref,
                    "outcome_price":px,"log_return":lr,"return_bps":lr*10000.0,
                    "event_type":r["event_type"],"payload":dict(r["payload"]) if r["payload"] else {}})
            return out

async def pending_count(pool,symbol=None):
    if symbol is None:
        return int(await pool.fetchval("SELECT count(*) FROM scientific_outcome_requests WHERE status='PENDING'"))
    return int(await pool.fetchval("SELECT count(*) FROM scientific_outcome_requests WHERE status='PENDING' AND symbol=$1",symbol))
