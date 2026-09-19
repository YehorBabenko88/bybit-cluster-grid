import json,uuid

SETUPS=("POC","BREAKOUT","FALSE_BREAK","VOLATILITY_CAPTURE")
VARIANTS=("BASE","REGIME","MARKOV","REGIME_MARKOV","ML","ML_MARKOV")

async def create_run(pool,dataset_id,strategy_name,symbols,config=None):
    run_id=uuid.uuid4()
    cfg=dict(config or {})
    async with pool.acquire() as c:
        async with c.transaction():
            ds=await c.fetchrow("SELECT status,dataset_hash FROM dataset_snapshots WHERE id=$1",dataset_id)
            if not ds or ds["status"]!="READY":raise ValueError("historical run requires READY immutable dataset")
            await c.execute("""INSERT INTO historical_experiment_runs
              (id,dataset_id,strategy_name,status,config,total_symbols)
              VALUES($1,$2,$3,'queued',$4::jsonb,$5)""",run_id,dataset_id,strategy_name,json.dumps(cfg),len(symbols))
            for symbol in sorted(set(symbols)):
                await c.execute("""INSERT INTO historical_experiment_checkpoints(run_id,symbol,status)
                  VALUES($1,$2,'queued') ON CONFLICT DO NOTHING""",run_id,symbol)
    return str(run_id)

async def claim_symbol(pool,run_id):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT symbol FROM historical_experiment_checkpoints
              WHERE run_id=$1 AND status IN ('queued','retry')
              ORDER BY symbol FOR UPDATE SKIP LOCKED LIMIT 1""",run_id)
            if not row:return None
            await c.execute("""UPDATE historical_experiment_checkpoints
              SET status='running',attempts=attempts+1,started_at=now(),last_error=NULL
              WHERE run_id=$1 AND symbol=$2""",run_id,row["symbol"])
            await c.execute("""UPDATE historical_experiment_runs SET status='running',
              started_at=COALESCE(started_at,now()) WHERE id=$1""",run_id)
            return row["symbol"]

async def finish_symbol(pool,run_id,symbol,error=None,retry=False):
    status="retry" if error and retry else ("failed" if error else "done")
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute("""UPDATE historical_experiment_checkpoints
              SET status=$3,finished_at=CASE WHEN $3 IN ('done','failed') THEN now() ELSE NULL END,last_error=$4
              WHERE run_id=$1 AND symbol=$2""",run_id,symbol,status,str(error)[:4000] if error else None)
            counts=await c.fetchrow("""SELECT count(*) FILTER(WHERE status='done') done,
              count(*) FILTER(WHERE status='failed') failed,
              count(*) FILTER(WHERE status IN ('queued','retry','running')) pending
              FROM historical_experiment_checkpoints WHERE run_id=$1""",run_id)
            final="done" if counts["pending"]==0 and counts["failed"]==0 else ("partial" if counts["pending"]==0 else "running")
            await c.execute("""UPDATE historical_experiment_runs SET completed_symbols=$2,failed_symbols=$3,
              status=$4,finished_at=CASE WHEN $4 IN ('done','partial') THEN now() ELSE NULL END,
              last_error=COALESCE($5,last_error) WHERE id=$1""",
              run_id,counts["done"],counts["failed"],final,str(error)[:4000] if error else None)
    return status

async def recover_stale(pool,run_id,stale_minutes=30,max_attempts=3):
    await pool.execute("""UPDATE historical_experiment_checkpoints SET
      status=CASE WHEN attempts<$3 THEN 'retry' ELSE 'failed' END,
      last_error=COALESCE(last_error,'recovered stale running checkpoint')
      WHERE run_id=$1 AND status='running' AND started_at<now()-($2*interval '1 minute')""",
      run_id,int(stale_minutes),int(max_attempts))
