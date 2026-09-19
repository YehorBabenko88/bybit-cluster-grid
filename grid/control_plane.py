import json, uuid

async def ensure_control_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS agent_commands(
          id uuid PRIMARY KEY,
          node_id text NOT NULL,
          action text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL DEFAULT 'queued',
          created_at timestamptz NOT NULL DEFAULT now(),
          delivered_at timestamptz,
          completed_at timestamptz,
          result jsonb,
          error text
        );
        CREATE INDEX IF NOT EXISTS agent_commands_node_status_idx
          ON agent_commands(node_id,status,created_at);
        """)

async def enqueue_command(pool,node_id,action,payload=None):
    cid=uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute("""INSERT INTO agent_commands(id,node_id,action,payload)
          VALUES($1,$2,$3,$4::jsonb)""",cid,node_id,action,json.dumps(payload or {}))
    return str(cid)

async def pending_commands(pool,node_id,limit=10):
    async with pool.acquire() as c:
        async with c.transaction():
            rows=await c.fetch("""SELECT * FROM agent_commands
              WHERE node_id=$1 AND status='queued'
              ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT $2""",node_id,limit)
            ids=[r["id"] for r in rows]
            if ids:
                await c.execute("""UPDATE agent_commands SET status='delivered',delivered_at=now()
                                   WHERE id=ANY($1::uuid[])""",ids)
            return [dict(r) for r in rows]

async def command_result(pool,command_id,ok,result=None,error=None):
    async with pool.acquire() as c:
        await c.execute("""UPDATE agent_commands SET status=$2,completed_at=now(),
          result=$3::jsonb,error=$4 WHERE id=$1""",command_id,
          "done" if ok else "failed",json.dumps(result or {}),error)
