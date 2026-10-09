import json

async def ensure_update_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS agent_releases(
          version text PRIMARY KEY,channel text NOT NULL DEFAULT 'stable',
          package_url text NOT NULL,sha256 text NOT NULL,enabled boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE TABLE IF NOT EXISTS agent_update_status(
          node_id text PRIMARY KEY,current_version text,target_version text,
          status text NOT NULL DEFAULT 'unknown',last_error text,
          health_acks integer NOT NULL DEFAULT 0,previous_version text,
          deadline timestamptz,updated_at timestamptz NOT NULL DEFAULT now()
        );
        ALTER TABLE agent_update_status ADD COLUMN IF NOT EXISTS health_acks integer NOT NULL DEFAULT 0;
        ALTER TABLE agent_update_status ADD COLUMN IF NOT EXISTS previous_version text;
        ALTER TABLE agent_update_status ADD COLUMN IF NOT EXISTS deadline timestamptz;
        CREATE TABLE IF NOT EXISTS rollout_state(
          version text PRIMARY KEY,phase text NOT NULL DEFAULT 'canary',
          canary_node text,required_health_acks integer NOT NULL DEFAULT 3,
          status text NOT NULL DEFAULT 'pending',created_at timestamptz NOT NULL DEFAULT now(),
          promoted_at timestamptz,last_error text
        );
        CREATE TABLE IF NOT EXISTS rollout_nodes(
          version text NOT NULL,node_id text NOT NULL,wave integer NOT NULL,
          status text NOT NULL DEFAULT 'pending',health_acks integer NOT NULL DEFAULT 0,
          deadline timestamptz,last_error text,updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY(version,node_id)
        );
        """)

async def register_release(pool,version,channel,package_url,sha256,metadata=None):
    async with pool.acquire() as c:
        await c.execute("""INSERT INTO agent_releases(version,channel,package_url,sha256,enabled,metadata)
          VALUES($1,$2,$3,$4,false,$5::jsonb)
          ON CONFLICT(version) DO UPDATE SET channel=EXCLUDED.channel,package_url=EXCLUDED.package_url,
          sha256=EXCLUDED.sha256,metadata=EXCLUDED.metadata""",
          version,channel,package_url,sha256,json.dumps(metadata or {}))

async def start_canary(pool,version,node_id,required_acks=3):
    async with pool.acquire() as c:
        rel=await c.fetchrow("SELECT version,package_url,sha256 FROM agent_releases WHERE version=$1",version)
        if not rel: raise ValueError("release not registered")
        await c.execute("""INSERT INTO rollout_state(version,phase,canary_node,required_health_acks,status)
          VALUES($1,'canary',$2,$3,'running')
          ON CONFLICT(version) DO UPDATE SET phase='canary',canary_node=EXCLUDED.canary_node,
          required_health_acks=EXCLUDED.required_health_acks,status='running',last_error=NULL""",
          version,node_id,required_acks)
        await c.execute("""INSERT INTO agent_update_status(node_id,target_version,status,health_acks,deadline)
          VALUES($1,$2,'awaiting_restart',0,now()+interval '5 minutes')
          ON CONFLICT(node_id) DO UPDATE SET target_version=$2,status='awaiting_restart',
          health_acks=0,deadline=now()+interval '5 minutes',last_error=NULL,updated_at=now()""",node_id,version)
        return dict(rel)

async def expired_canaries(pool):
    async with pool.acquire() as c:
        rows=await c.fetch("""SELECT r.version,r.canary_node FROM rollout_state r
          JOIN agent_update_status s ON s.node_id=r.canary_node AND s.target_version=r.version
          WHERE r.status='running' AND s.deadline IS NOT NULL AND s.deadline<now()""")
        for row in rows:
            await c.execute("""UPDATE rollout_state SET status='failed',
              last_error='canary health timeout' WHERE version=$1""",row["version"])
            await c.execute("""UPDATE agent_update_status SET status='rollback_pending',
              last_error='canary health timeout',updated_at=now() WHERE node_id=$1""",row["canary_node"])
        return [dict(r) for r in rows]

def release_health_ok(heartbeat):
    if not heartbeat:
        return False,"missing heartbeat"
    if not heartbeat.get("integrity_ok",False):
        return False,"integrity"
    if str(heartbeat.get("pressure_state","CRITICAL"))=="CRITICAL":
        return False,"critical_pressure"
    # db_write_failures is cumulative and may include failures that have
    # already recovered. Only reject failures observed in the latest interval.
    # Older workers omit this field; their cumulative counter is not a
    # reliable signal of current health.
    if int(heartbeat.get("db_write_failures_recent",0) or 0)>0:
        return False,"db_write_failures_recent"
    if float(heartbeat.get("db_queue_ratio",0) or 0)>=0.8:
        return False,"db_queue_pressure"
    if float(heartbeat.get("db_spool_ratio",0) or 0)>=0.8:
        return False,"db_spool_pressure"
    return True,None

async def note_heartbeat(pool,node_id,version,heartbeat=None):
    ok,reason=release_health_ok(heartbeat)
    if not ok:
        return "unhealthy:"+str(reason)
    async with pool.acquire() as c:
        row=await c.fetchrow("""SELECT version,required_health_acks FROM rollout_state
          WHERE canary_node=$1 AND status='running' ORDER BY created_at DESC LIMIT 1""",node_id)
        if not row or row["version"]!=version: return None
        await c.execute("""INSERT INTO agent_update_status(node_id,current_version,target_version,status,health_acks)
          VALUES($1,$2,$2,'verifying',1)
          ON CONFLICT(node_id) DO UPDATE SET current_version=$2,target_version=$2,status='verifying',
          health_acks=CASE WHEN agent_update_status.current_version=$2 THEN agent_update_status.health_acks+1 ELSE 1 END,
          updated_at=now()""",node_id,version)
        acks=await c.fetchval("SELECT health_acks FROM agent_update_status WHERE node_id=$1",node_id)
        if acks>=row["required_health_acks"]:
            await c.execute("UPDATE rollout_state SET status='healthy',promoted_at=now() WHERE version=$1",version)
            await c.execute("UPDATE agent_update_status SET status='healthy' WHERE node_id=$1",node_id)
            return "healthy"
        return "verifying"

async def promote_stable(pool,version):
    async with pool.acquire() as c:
        state=await c.fetchrow("SELECT * FROM rollout_state WHERE version=$1",version)
        if not state or state["status"]!="healthy": raise ValueError("canary is not healthy")
        await c.execute("UPDATE agent_releases SET channel='stable',enabled=true WHERE version=$1",version)
        await c.execute("UPDATE rollout_state SET phase='stable',status='promoted',promoted_at=now() WHERE version=$1",version)

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
