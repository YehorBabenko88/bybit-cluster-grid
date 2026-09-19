import math
from .control_plane import enqueue_command

WAVE_PCTS=(0.25,0.50,1.00)

def build_waves(node_ids,canary_node):
    remaining=sorted(n for n in set(node_ids) if n!=canary_node)
    total=len(remaining)
    if not total: return []
    boundaries=[]
    last=0
    for pct in WAVE_PCTS:
        end=total if pct>=1 else max(last,math.ceil(total*pct))
        boundaries.append(remaining[last:end])
        last=end
    return [w for w in boundaries if w]

async def begin_stable_rollout(pool,version,node_ids,canary_node):
    waves=build_waves(node_ids,canary_node)
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS rollout_nodes(
          version text NOT NULL,node_id text NOT NULL,wave integer NOT NULL,
          status text NOT NULL DEFAULT 'pending',health_acks integer NOT NULL DEFAULT 0,
          deadline timestamptz,last_error text,updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY(version,node_id)
        )""")
        for i,wave in enumerate(waves,1):
            for node in wave:
                await c.execute("""INSERT INTO rollout_nodes(version,node_id,wave,status)
                  VALUES($1,$2,$3,'pending') ON CONFLICT(version,node_id) DO NOTHING""",version,node,i)
        await c.execute("""UPDATE rollout_state SET phase='stable_wave_1',status='rolling'
          WHERE version=$1""",version)
    return await launch_next_wave(pool,version)

async def launch_next_wave(pool,version):
    async with pool.acquire() as c:
        failed=await c.fetchval("""SELECT count(*) FROM rollout_nodes
          WHERE version=$1 AND status IN ('failed','rollback_pending')""",version)
        if failed:
            await c.execute("""UPDATE rollout_state SET status='failed',
              last_error='stable rollout node failed' WHERE version=$1""",version)
            return []
        active=await c.fetchval("""SELECT count(*) FROM rollout_nodes
          WHERE version=$1 AND status IN ('queued','verifying')""",version)
        if active: return []
        wave=await c.fetchval("""SELECT min(wave) FROM rollout_nodes
          WHERE version=$1 AND status='pending'""",version)
        if wave is None:
            await c.execute("""UPDATE rollout_state SET phase='complete',status='complete',
              promoted_at=now() WHERE version=$1""",version)
            return []
        rel=await c.fetchrow("SELECT version,package_url,sha256 FROM agent_releases WHERE version=$1",version)
        nodes=await c.fetch("SELECT node_id FROM rollout_nodes WHERE version=$1 AND wave=$2 AND status='pending'",version,wave)
        for row in nodes:
            await c.execute("""UPDATE rollout_nodes SET status='queued',
              deadline=now()+interval '5 minutes',health_acks=0,updated_at=now()
              WHERE version=$1 AND node_id=$2""",version,row["node_id"])
        await c.execute("UPDATE rollout_state SET phase=$2 WHERE version=$1",version,f"stable_wave_{wave}")
    payload=dict(rel)
    for row in nodes:
        await enqueue_command(pool,row["node_id"],"update",payload)
    return [r["node_id"] for r in nodes]

async def note_rollout_heartbeat(pool,node_id,version,required_acks=3):
    async with pool.acquire() as c:
        row=await c.fetchrow("""SELECT status,health_acks FROM rollout_nodes
          WHERE version=$1 AND node_id=$2""",version,node_id)
        if not row or row["status"] not in ("queued","verifying"): return None
        acks=row["health_acks"]+1
        status="healthy" if acks>=required_acks else "verifying"
        await c.execute("""UPDATE rollout_nodes SET status=$3,health_acks=$4,
          updated_at=now() WHERE version=$1 AND node_id=$2""",version,node_id,status,acks)
    if status=="healthy":
        await launch_next_wave(pool,version)
    return status

async def expire_rollout_nodes(pool):
    async with pool.acquire() as c:
        rows=await c.fetch("""UPDATE rollout_nodes SET status='rollback_pending',
          last_error='health timeout',updated_at=now()
          WHERE status IN ('queued','verifying') AND deadline<now()
          RETURNING version,node_id""")
        versions={r["version"] for r in rows}
        for version in versions:
            await c.execute("""UPDATE rollout_state SET status='failed',
              last_error='stable rollout health timeout' WHERE version=$1""",version)
        return [dict(r) for r in rows]
