import json

async def ensure_update_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS agent_releases(
          version text PRIMARY KEY,
          channel text NOT NULL DEFAULT 'stable',
          package_url text NOT NULL,
          sha256 text NOT NULL,
          enabled boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE TABLE IF NOT EXISTS agent_update_status(
          node_id text PRIMARY KEY,current_version text,target_version text,
          status text NOT NULL DEFAULT 'unknown',last_error text,
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        """)

async def desired_release(pool,channel="stable"):
    async with pool.acquire() as c:
        row=await c.fetchrow("""SELECT version,package_url,sha256,metadata FROM agent_releases
          WHERE channel=$1 AND enabled=true ORDER BY created_at DESC LIMIT 1""",channel)
        return dict(row) if row else None

async def report_update(pool,node_id,current,target,status,error=None):
    async with pool.acquire() as c:
        await c.execute("""INSERT INTO agent_update_status(node_id,current_version,target_version,status,last_error)
          VALUES($1,$2,$3,$4,$5)
          ON CONFLICT(node_id) DO UPDATE SET current_version=EXCLUDED.current_version,
          target_version=EXCLUDED.target_version,status=EXCLUDED.status,last_error=EXCLUDED.last_error,
          updated_at=now()""",node_id,current,target,status,error)
