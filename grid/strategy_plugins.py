import hashlib, json, re

SAFE_NAME=re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

async def ensure_plugin_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS strategy_plugins(
          strategy_name text NOT NULL,
          strategy_version text NOT NULL,
          sha256 text NOT NULL,
          source_code text NOT NULL,
          enabled boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          PRIMARY KEY(strategy_name,strategy_version)
        );
        """)

def digest_source(source_code):
    return hashlib.sha256(source_code.encode("utf-8")).hexdigest()

async def register_plugin(pool,name,version,source_code,metadata=None):
    if not SAFE_NAME.match(name) or not SAFE_NAME.match(version):
        raise ValueError("invalid strategy name/version")
    sha=digest_source(source_code)
    async with pool.acquire() as c:
        await c.execute("""INSERT INTO strategy_plugins
          (strategy_name,strategy_version,sha256,source_code,metadata)
          VALUES($1,$2,$3,$4,$5::jsonb)
          ON CONFLICT(strategy_name,strategy_version) DO UPDATE SET
            sha256=EXCLUDED.sha256,
            source_code=EXCLUDED.source_code,
            enabled=true,
            metadata=EXCLUDED.metadata""",
            name,version,sha,source_code,json.dumps(metadata or {}))
    return sha

async def get_plugin(pool,name,version):
    async with pool.acquire() as c:
        row=await c.fetchrow("""SELECT * FROM strategy_plugins
          WHERE strategy_name=$1 AND strategy_version=$2 AND enabled=true""",name,version)
        return dict(row) if row else None

async def list_plugins(pool):
    async with pool.acquire() as c:
        rows=await c.fetch("""SELECT strategy_name,strategy_version,sha256,enabled,created_at,metadata
                              FROM strategy_plugins ORDER BY strategy_name,strategy_version""")
        return [dict(r) for r in rows]
