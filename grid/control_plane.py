import json, uuid

ALLOWED_ACTIONS={"pause","resume","stop","start","restart","update","rollback","uninstall","log_tail","repair"}

async def ensure_control_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS agent_commands(
          id uuid PRIMARY KEY,node_id text NOT NULL,action text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,status text NOT NULL DEFAULT 'queued',
          created_at timestamptz NOT NULL DEFAULT now(),delivered_at timestamptz,
          lease_until timestamptz,attempts integer NOT NULL DEFAULT 0,
          max_attempts integer NOT NULL DEFAULT 5,completed_at timestamptz,result jsonb,error text
        );
        ALTER TABLE agent_commands ADD COLUMN IF NOT EXISTS lease_until timestamptz;
        ALTER TABLE agent_commands ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
        ALTER TABLE agent_commands ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 5;
        CREATE INDEX IF NOT EXISTS agent_commands_node_status_idx
          ON agent_commands(node_id,status,created_at);
        """)

async def enqueue_command(pool,node_id,action,payload=None):
    if action not in ALLOWED_ACTIONS: raise ValueError("unsupported control action")
    cid=uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute("""INSERT INTO agent_commands(id,node_id,action,payload)
          VALUES($1,$2,$3,$4::jsonb)""",cid,node_id,action,json.dumps(payload or {}))
    return str(cid)

async def pending_commands(pool,node_id,limit=10):
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute("""UPDATE agent_commands SET status='queued',lease_until=NULL
              WHERE node_id=$1 AND status='delivered' AND lease_until<now()
                AND attempts<max_attempts""",node_id)
            await c.execute("""UPDATE agent_commands SET status='failed',completed_at=now(),
              error=COALESCE(error,'command delivery attempts exhausted')
              WHERE node_id=$1 AND status='delivered' AND lease_until<now()
                AND attempts>=max_attempts""",node_id)
            rows=await c.fetch("""SELECT * FROM agent_commands
              WHERE node_id=$1 AND status='queued'
              ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT $2""",node_id,limit)
            ids=[r["id"] for r in rows]
            if ids:
                await c.execute("""UPDATE agent_commands SET status='delivered',delivered_at=now(),
                  lease_until=now()+interval '2 minutes',attempts=attempts+1
                  WHERE id=ANY($1::uuid[])""",ids)
            return [dict(r) for r in rows]

async def command_result(pool,command_id,ok,result=None,error=None,node_id=None):
    async with pool.acquire() as c:
        if node_id is None:
            changed=await c.execute("""UPDATE agent_commands SET status=$2,completed_at=now(),
              lease_until=NULL,result=$3::jsonb,error=$4 WHERE id=$1""",command_id,
              "done" if ok else "failed",json.dumps(result or {}),error)
        else:
            changed=await c.execute("""UPDATE agent_commands SET status=$2,completed_at=now(),
              lease_until=NULL,result=$3::jsonb,error=$4
              WHERE id=$1 AND node_id=$5""",command_id,
              "done" if ok else "failed",json.dumps(result or {}),error,str(node_id))
        ok=str(changed).endswith(" 1")
        if node_id is not None and not ok:
            raise ValueError("command does not belong to authenticated node")
        return ok
