import hashlib, secrets, uuid
from datetime import datetime, timezone

def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

async def ensure_enrollment_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS enrollment_tokens(
          token_hash text PRIMARY KEY,
          label text,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS agent_credentials(
          node_id text PRIMARY KEY,
          credential_hash text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          revoked_at timestamptz
        );
        """)

async def create_enrollment_token(pool,label,expires_at):
    token=secrets.token_urlsafe(32)
    async with pool.acquire() as c:
        await c.execute("INSERT INTO enrollment_tokens(token_hash,label,expires_at) VALUES($1,$2,$3)",
                        hash_token(token),label,expires_at)
    return token

async def enroll(pool,token,node_id):
    th=hash_token(token)
    credential=secrets.token_urlsafe(48)
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("""SELECT * FROM enrollment_tokens
              WHERE token_hash=$1 AND used_at IS NULL AND expires_at>now()
              FOR UPDATE""",th)
            if not row: raise ValueError("invalid/expired enrollment token")
            await c.execute("UPDATE enrollment_tokens SET used_at=now() WHERE token_hash=$1",th)
            await c.execute("""INSERT INTO agent_credentials(node_id,credential_hash)
              VALUES($1,$2) ON CONFLICT(node_id) DO UPDATE SET credential_hash=EXCLUDED.credential_hash,
              revoked_at=NULL,created_at=now()""",node_id,hash_token(credential))
    return credential

async def authenticate_agent(pool,node_id,credential):
    async with pool.acquire() as c:
        expected=await c.fetchval("""SELECT credential_hash FROM agent_credentials
          WHERE node_id=$1 AND revoked_at IS NULL""",node_id)
    return bool(expected) and secrets.compare_digest(expected,hash_token(credential))
