import json

async def set_consumer_watermark(pool,dataset,consumer,symbol,through,required=True):
    await pool.execute("""INSERT INTO consumer_watermarks(dataset,consumer,symbol,consumed_through,required)
      VALUES($1,$2,$3,$4,$5) ON CONFLICT(dataset,consumer,symbol) DO UPDATE SET
      consumed_through=GREATEST(consumer_watermarks.consumed_through,EXCLUDED.consumed_through),
      required=EXCLUDED.required,updated_at=now()""",dataset,consumer,symbol,through,bool(required))

async def set_consumer_watermarks(pool,items):
    """Batch monotonic watermark updates into one round trip."""
    rows=[(d,c,s,t,bool(req)) for d,c,s,t,req in items]
    if not rows:return
    await pool.executemany("""INSERT INTO consumer_watermarks(dataset,consumer,symbol,consumed_through,required)
      VALUES($1,$2,$3,$4,$5) ON CONFLICT(dataset,consumer,symbol) DO UPDATE SET
      consumed_through=GREATEST(consumer_watermarks.consumed_through,EXCLUDED.consumed_through),
      required=EXCLUDED.required,updated_at=now()""",rows)

async def safe_cutoff(pool,dataset,symbol,age_cutoff):
    """Never pass the slowest required consumer and never cross an active retention hold."""
    wm=await pool.fetchval("""SELECT min(consumed_through) FROM consumer_watermarks
      WHERE dataset=$1 AND symbol=$2 AND required=true""",dataset,symbol)
    if wm is None:return None
    cutoff=min(age_cutoff,wm)
    hold=await pool.fetchval("""SELECT min(COALESCE(from_ts,'-infinity'::timestamptz))
      FROM retention_holds WHERE dataset=$1 AND (symbol IS NULL OR symbol=$2)
      AND (expires_at IS NULL OR expires_at>now())
      AND (through_ts IS NULL OR through_ts>='-infinity'::timestamptz)""",dataset,symbol)
    if hold is not None: cutoff=min(cutoff,hold)
    return cutoff

async def put_control_state(pool,key,value,node_id,expected_version=None):
    if expected_version is None:
        row=await pool.fetchrow("""INSERT INTO replicated_control_state(state_key,value,updated_by)
          VALUES($1,$2::jsonb,$3) ON CONFLICT(state_key) DO UPDATE SET value=EXCLUDED.value,
          version=replicated_control_state.version+1,updated_at=now(),updated_by=EXCLUDED.updated_by
          RETURNING version""",key,json.dumps(value),node_id)
    else:
        row=await pool.fetchrow("""UPDATE replicated_control_state SET value=$2::jsonb,version=version+1,
          updated_at=now(),updated_by=$3 WHERE state_key=$1 AND version=$4 RETURNING version""",
          key,json.dumps(value),node_id,int(expected_version))
    return row["version"] if row else None

async def get_control_state(pool,key):
    row=await pool.fetchrow("SELECT value,version,updated_at,updated_by FROM replicated_control_state WHERE state_key=$1",key)
    return dict(row) if row else None
