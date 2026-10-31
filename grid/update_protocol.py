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
        ALTER TABLE rollout_state ADD COLUMN IF NOT EXISTS protocol integer NOT NULL DEFAULT 1;
        """)

async def register_release(pool,version,channel,package_url,sha256,metadata=None):
    async with pool.acquire() as c:
        await c.execute("""INSERT INTO agent_releases(version,channel,package_url,sha256,enabled,metadata)
          VALUES($1,$2,$3,$4,false,$5::jsonb)
          ON CONFLICT(version) DO UPDATE SET channel=EXCLUDED.channel,package_url=EXCLUDED.package_url,
          sha256=EXCLUDED.sha256,metadata=EXCLUDED.metadata WHERE agent_releases.metadata->>'schema' IS DISTINCT FROM 'grid.unified.release.v3'""",
          version,channel,package_url,sha256,json.dumps(metadata or {}))

async def start_canary(pool,version,node_id,required_acks=3):
    async with pool.acquire() as c:
        rel=await c.fetchrow("SELECT version,package_url,sha256,metadata FROM agent_releases WHERE version=$1",version)
        if not rel: raise ValueError("release not registered")
        metadata=rel.get('metadata') or {}
        if isinstance(metadata,str):metadata=json.loads(metadata)
        if metadata.get('schema')=='grid.unified.release.v3':raise ValueError('unified release requires fenced v3 rollout')
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
          WHERE r.status='running' AND s.deadline IS NOT NULL AND s.deadline<now()
          AND r.version NOT IN (SELECT version FROM agent_releases WHERE metadata->>'schema'='grid.unified.release.v3')""")
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
    if int(heartbeat.get("db_write_failures",0) or 0)>0:
        return False,"db_write_failures"
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
        metadata=await c.fetchval('SELECT metadata FROM agent_releases WHERE version=$1',version)
        if isinstance(metadata,str):metadata=json.loads(metadata)
        if isinstance(metadata,dict) and metadata.get('schema')=='grid.unified.release.v3':raise ValueError('unified release requires fenced v3 heartbeat')
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
        if not state or state["status"]!="healthy" or state.get('protocol',1)!=1: raise ValueError("canary is not healthy")
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

# v3 uses the same Grid release/rollout tables. No independent leader or queue.
async def ensure_unified_update_schema(pool):
    await ensure_update_schema(pool)
    async with pool.acquire() as c:
        await c.execute("""ALTER TABLE rollout_state ADD COLUMN IF NOT EXISTS protocol integer NOT NULL DEFAULT 1;
            ALTER TABLE rollout_state ADD COLUMN IF NOT EXISTS generation bigint NOT NULL DEFAULT 0;
            ALTER TABLE rollout_state ADD COLUMN IF NOT EXISTS manifest_sha256 text;
            ALTER TABLE rollout_state ADD COLUMN IF NOT EXISTS admin_stopped boolean NOT NULL DEFAULT false;
            ALTER TABLE rollout_state ADD COLUMN IF NOT EXISTS leader_owner text;
            ALTER TABLE rollout_state ADD COLUMN IF NOT EXISTS leader_epoch bigint;
            ALTER TABLE rollout_nodes ADD COLUMN IF NOT EXISTS generation bigint NOT NULL DEFAULT 0;""")


async def begin_unified_rollout(pool,manifest_bytes,signature,*,publisher_pin,verify_signature,node_ids,canary_node):
    """Admission precedes persistence; publisher pin must come from owner policy.

    No reenabling/reinitializing an existing version. Legacy wave launcher must
    not be invoked for protocol3: the consensus-backed controller calls claim
    and sends the returned permit through existing authenticated Grid commands.
    """
    import hashlib,re
    from unified_system.release_manifest import parse_manifest
    if verify_signature(manifest_bytes,signature,publisher_pin) is not True:raise ValueError('publisher signature required')
    m=parse_manifest(manifest_bytes,expected_publisher=publisher_pin)
    nodes=list(node_ids)
    if (not 2<=len(nodes)<=6 or len(set(nodes))!=len(nodes) or canary_node not in nodes or
        any(type(n) is not str or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',n) or n.upper() in ('LS5','PC4','ADMINIT') for n in nodes)):raise ValueError('ephemeral rollout roster')
    digest=hashlib.sha256(manifest_bytes).hexdigest()
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute('SELECT pg_advisory_xact_lock(73531003)')
            if await c.fetchval("SELECT EXISTS(SELECT 1 FROM agent_releases WHERE version=$1)",m['release_id']):raise ValueError('immutable release already registered')
            prior=await c.fetchval("SELECT COALESCE(max((metadata->'manifest'->>'sequence')::bigint),0) FROM agent_releases WHERE metadata->>'schema'='grid.unified.release.v3'")
            if m['sequence']<=prior:raise ValueError('nonmonotonic unified sequence')
            if await c.fetchval("SELECT EXISTS(SELECT 1 FROM rollout_state WHERE protocol=3 AND status IN ('running','rolling'))"):raise ValueError('another unified rollout active')
            await c.execute("INSERT INTO agent_releases(version,channel,package_url,sha256,enabled,metadata) VALUES($1,'canary','local:immutable-six-module',$2,false,$3::jsonb)",m['release_id'],digest,json.dumps({'schema':'grid.unified.release.v3','manifest':m}))
            await c.execute("INSERT INTO rollout_state(version,phase,canary_node,required_health_acks,status,protocol,generation,manifest_sha256) VALUES($1,'canary',$2,1,'running',3,0,$3)",m['release_id'],canary_node,digest)
            ordered=[canary_node]+sorted(n for n in nodes if n!=canary_node)
            for wave,node in enumerate(ordered):
                await c.execute("INSERT INTO rollout_nodes(version,node_id,wave,status) VALUES($1,$2,$3,'pending')",m['release_id'],node,wave)
    return digest


async def claim_unified_node(pool,version,*,lease_guard):
    """Serialize canary then rolling nodes; one restart in flight fleet-wide."""
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute('SELECT pg_advisory_xact_lock(73531003)')
            state=await c.fetchrow('SELECT * FROM rollout_state WHERE version=$1 FOR UPDATE',version)
            if not state or state['protocol']!=3 or state['admin_stopped'] or state['status'] not in ('running','rolling'):return None
            if await c.fetchval("SELECT EXISTS(SELECT 1 FROM rollout_nodes WHERE status IN ('queued','verifying','rollback_pending'))"):return None
            if await c.fetchval("SELECT EXISTS(SELECT 1 FROM rollout_nodes WHERE version=$1 AND status='failed')",version):return None
            row=await c.fetchrow("SELECT node_id,wave FROM rollout_nodes WHERE version=$1 AND status='pending' ORDER BY wave,node_id LIMIT 1 FOR UPDATE",version)
            if not row:
                await c.execute("UPDATE rollout_state SET phase='complete',status='complete' WHERE version=$1",version);return None
            lease=await lease_guard()
            if set(lease)!={'owner','epoch'} or not isinstance(lease['owner'],str) or type(lease['epoch']) is not int or lease['epoch']<=0:raise ValueError('current DCS lease required')
            await _fence_unified_leader(c,lease)
            generation=state['generation']+1
            await c.execute("UPDATE rollout_state SET generation=$2,phase=$3,status='rolling',leader_owner=$4,leader_epoch=$5 WHERE version=$1",version,generation,'canary' if row['wave']==0 else 'rolling',lease['owner'],lease['epoch'])
            await c.execute("UPDATE rollout_nodes SET status='queued',generation=$3,deadline=now()+interval '5 minutes' WHERE version=$1 AND node_id=$2",version,row['node_id'],generation)
            return dict(schema='grid.unified.update-permit.v3',version=version,node_id=row['node_id'],generation=generation,manifest_sha256=state['manifest_sha256'],status='queued',leader_owner=lease['owner'],leader_epoch=lease['epoch'])


async def acknowledge_unified_node(pool,permit,*,healthy,lease_guard,health=None):
    if type(healthy) is not bool:raise ValueError('explicit health verdict required')
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute('SELECT pg_advisory_xact_lock(73531003)')
            state=await c.fetchrow('SELECT * FROM rollout_state WHERE version=$1 FOR UPDATE',permit['version'])
            if (not state or state['protocol']!=3 or state['admin_stopped'] or state['generation']!=permit['generation'] or state['manifest_sha256']!=permit['manifest_sha256'] or state['status']!='rolling'):raise ValueError('stale or stopped rollout')
            row=await c.fetchrow('SELECT * FROM rollout_nodes WHERE version=$1 AND node_id=$2 FOR UPDATE',permit['version'],permit['node_id'])
            if not row or row['generation']!=permit['generation'] or row['status']!='queued':raise ValueError('stale node permit')
            lease=await lease_guard()
            if (lease['owner'],lease['epoch'])!=(state['leader_owner'],state['leader_epoch']) or (permit['leader_owner'],permit['leader_epoch'])!=(lease['owner'],lease['epoch']):raise ValueError('stale leader epoch')
            await _fence_unified_leader(c,lease)
            # Expired leases never become healthy from a delayed acknowledgement.
            expired=await c.fetchval('SELECT deadline<now() FROM rollout_nodes WHERE version=$1 AND node_id=$2',permit['version'],permit['node_id'])
            if expired:raise ValueError('expired rollout permit')
            if healthy:
                metadata=await c.fetchval('SELECT metadata FROM agent_releases WHERE version=$1',permit['version'])
                if isinstance(metadata,str):metadata=json.loads(metadata)
                manifest=metadata['manifest']
                expected=dict(release_id=permit['version'],release_sha256=state['manifest_sha256'],ready=True,modules={k:dict(version=v['version'],ready=True) for k,v in manifest['modules'].items()})
                if health!=expected:raise ValueError('actual six-module functional health required')
            await c.execute('UPDATE rollout_nodes SET status=$3,updated_at=now() WHERE version=$1 AND node_id=$2',permit['version'],permit['node_id'],'healthy' if healthy else 'failed')
            if not healthy:await c.execute("UPDATE rollout_state SET status='failed',last_error='six-module health failed' WHERE version=$1",permit['version'])


async def stop_unified_rollout(pool,version):
    async with pool.acquire() as c:
        await c.execute("UPDATE rollout_state SET admin_stopped=true,status='stopped' WHERE version=$1 AND protocol=3",version)


async def _fence_unified_leader(c,lease):
    """Fence PGepoch under row lock; DCSsession validated by caller lease_guard.

    DCS and PostgreSQL do not form one atomic transaction. Fail closed on either
    unavailable authority; never present this recheck as cross-store consensus.
    """
    row=await c.fetchrow("SELECT owner,metadata,lease_until>clock_timestamp() AS alive FROM service_leases WHERE service_key='control-plane-leader' FOR UPDATE")
    metadata=row['metadata'] if row else None
    if isinstance(metadata,str):metadata=json.loads(metadata)
    if not row or not row['alive'] or row['owner']!=lease['owner'] or not isinstance(metadata,dict) or metadata.get('epoch')!=lease['epoch']:raise ValueError('stale PostgreSQL leader fence')
