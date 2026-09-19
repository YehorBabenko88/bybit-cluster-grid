import json, logging, uuid
log=logging.getLogger("strategy_jobs")

async def ensure_strategy_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS strategy_jobs(
          id uuid PRIMARY KEY,
          strategy_name text NOT NULL,
          strategy_version text NOT NULL DEFAULT '1',
          params jsonb NOT NULL DEFAULT '{}'::jsonb,
          symbols jsonb NOT NULL DEFAULT '[]'::jsonb,
          start_ts timestamptz,
          end_ts timestamptz,
          status text NOT NULL DEFAULT 'queued',
          assigned_node text,
          priority integer NOT NULL DEFAULT 100,
          attempts integer NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now(),
          started_at timestamptz,
          finished_at timestamptz,
          error text
        );
        ALTER TABLE strategy_jobs ADD COLUMN IF NOT EXISTS priority integer NOT NULL DEFAULT 100;
        ALTER TABLE strategy_jobs ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
        CREATE INDEX IF NOT EXISTS strategy_jobs_status_idx ON strategy_jobs(status,priority,created_at);

        CREATE TABLE IF NOT EXISTS strategy_results(
          job_id uuid NOT NULL REFERENCES strategy_jobs(id) ON DELETE CASCADE,
          symbol text NOT NULL,
          ts timestamptz NOT NULL,
          result_type text NOT NULL,
          payload jsonb NOT NULL,
          PRIMARY KEY(job_id,symbol,ts,result_type)
        );
        """)

async def submit_job(pool,strategy_name,strategy_version="1",params=None,symbols=None,start_ts=None,end_ts=None,priority=100):
    job_id=uuid.uuid4()
    async with pool.acquire() as c:
        exists=await c.fetchval("""SELECT EXISTS(
          SELECT 1 FROM strategy_plugins
          WHERE strategy_name=$1 AND strategy_version=$2 AND enabled=true
        )""",strategy_name,strategy_version)
        if not exists:
            raise ValueError(f"strategy plugin not registered: {strategy_name} v{strategy_version}")
        await c.execute("""INSERT INTO strategy_jobs
          (id,strategy_name,strategy_version,params,symbols,start_ts,end_ts,priority)
          VALUES($1,$2,$3,$4::jsonb,$5::jsonb,$6,$7,$8)""",
          job_id,strategy_name,strategy_version,json.dumps(params or {}),json.dumps(symbols or []),
          start_ts,end_ts,int(priority))
    return str(job_id)

async def claim_job(pool,node_id):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM strategy_jobs
              WHERE status='queued'
              ORDER BY priority ASC,created_at ASC
              FOR UPDATE SKIP LOCKED LIMIT 1""")
            if not row: return None
            await c.execute("""UPDATE strategy_jobs
              SET status='running',assigned_node=$2,started_at=now(),attempts=attempts+1,error=NULL
              WHERE id=$1""",row["id"],node_id)
            row=dict(row); row["assigned_node"]=node_id; return row

async def requeue_job(pool,job_id,reason):
    async with pool.acquire() as c:
        await c.execute("""UPDATE strategy_jobs SET status='queued',assigned_node=NULL,started_at=NULL,error=$2
                           WHERE id=$1""",job_id,reason)

async def finish_job(pool,job_id,error=None):
    async with pool.acquire() as c:
        await c.execute("""UPDATE strategy_jobs SET status=$2,finished_at=now(),error=$3 WHERE id=$1""",
                        job_id,"failed" if error else "done",error)


async def recover_stale_jobs(pool,stale_seconds,max_attempts=5):
    return await pool.execute("""UPDATE strategy_jobs SET
      status=CASE WHEN attempts<$2 THEN 'queued' ELSE 'failed' END,
      assigned_node=NULL,started_at=NULL,
      finished_at=CASE WHEN attempts>=$2 THEN now() ELSE NULL END,
      error=COALESCE(error,'recovered stale strategy worker')
      WHERE status='running' AND started_at IS NOT NULL
        AND started_at<now()-($1::int*interval '1 second')""",
      int(stale_seconds),int(max_attempts))
