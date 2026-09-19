import asyncio, json, logging, uuid
from datetime import datetime, timezone
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
          created_at timestamptz NOT NULL DEFAULT now(),
          started_at timestamptz,
          finished_at timestamptz,
          error text
        );
        CREATE INDEX IF NOT EXISTS strategy_jobs_status_idx ON strategy_jobs(status,created_at);

        CREATE TABLE IF NOT EXISTS strategy_results(
          job_id uuid NOT NULL REFERENCES strategy_jobs(id) ON DELETE CASCADE,
          symbol text NOT NULL,
          ts timestamptz NOT NULL,
          result_type text NOT NULL,
          payload jsonb NOT NULL,
          PRIMARY KEY(job_id,symbol,ts,result_type)
        );
        """)

async def submit_job(pool,strategy_name,params=None,symbols=None,start_ts=None,end_ts=None):
    job_id=uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute("""INSERT INTO strategy_jobs
          (id,strategy_name,params,symbols,start_ts,end_ts)
          VALUES($1,$2,$3::jsonb,$4::jsonb,$5,$6)""",
          job_id,strategy_name,json.dumps(params or {}),json.dumps(symbols or []),start_ts,end_ts)
    return str(job_id)

async def claim_job(pool,node_id):
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM strategy_jobs
              WHERE status='queued'
              ORDER BY created_at
              FOR UPDATE SKIP LOCKED LIMIT 1""")
            if not row: return None
            await c.execute("""UPDATE strategy_jobs SET status='running',assigned_node=$2,started_at=now()
                               WHERE id=$1""",row["id"],node_id)
            return dict(row)

async def finish_job(pool,job_id,error=None):
    async with pool.acquire() as c:
        await c.execute("""UPDATE strategy_jobs SET status=$2,finished_at=now(),error=$3 WHERE id=$1""",
                        job_id,"failed" if error else "done",error)
