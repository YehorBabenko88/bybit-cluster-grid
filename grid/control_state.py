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

async def put_control_state(pool,key,value,node_id,expected_version=None,*,service_fence=None):
    if service_fence is not None:
        if (not isinstance(service_fence,dict) or set(service_fence)!={"service_key","owner","epoch"}
                or service_fence["service_key"]!="control-plane-leader"
                or not isinstance(service_fence["owner"],str)
                or not 1<=len(service_fence["owner"])<=128 or service_fence["owner"]!=node_id
                or type(service_fence["epoch"]) is not int or not 0<service_fence["epoch"]<2**63
                or type(expected_version) is not int or not 0<=expected_version<2**63):
            raise ValueError("invalid control state service fence")
        # Lock the exact service row in the same statement as the version CAS.
        # A concurrent lease revocation must finish first or wait for this short
        # transaction; no network I/O belongs inside this transaction.
        guard="""WITH active_service AS MATERIALIZED (
            SELECT 1 FROM service_leases WHERE service_key=$5 AND owner=$6
            AND (metadata->>'epoch')::bigint=$7 AND lease_until>clock_timestamp()
            FOR SHARE) """
        if expected_version==0:
            mutation="""INSERT INTO replicated_control_state(state_key,value,updated_by)
                SELECT $1,$2::jsonb,$3 FROM active_service WHERE $4::bigint=0
                ON CONFLICT(state_key) DO NOTHING RETURNING version"""
        else:
            mutation="""UPDATE replicated_control_state SET value=$2::jsonb,version=version+1,
                updated_at=now(),updated_by=$3 WHERE state_key=$1 AND version=$4
                AND EXISTS(SELECT 1 FROM active_service) RETURNING version"""
        row=await pool.fetchrow(guard+mutation,key,json.dumps(value),node_id,expected_version,
            service_fence["service_key"],service_fence["owner"],service_fence["epoch"])
        return row["version"] if row else None
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
