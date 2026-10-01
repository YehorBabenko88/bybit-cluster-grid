import hashlib
import secrets


AUTHORIZED_INSTALL_MODES = {"PILOT", "NORMAL"}


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_authorized_mode(value):
    mode = str(value or "").upper()
    if mode not in AUTHORIZED_INSTALL_MODES:
        raise ValueError("invalid authorized install mode")
    return mode


async def ensure_enrollment_schema(pool):
    async with pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS enrollment_tokens(
          token_hash text PRIMARY KEY,
          label text,
          authorized_mode text NOT NULL DEFAULT 'UNKNOWN',
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        ALTER TABLE enrollment_tokens
          ADD COLUMN IF NOT EXISTS authorized_mode text NOT NULL DEFAULT 'UNKNOWN';

        CREATE TABLE IF NOT EXISTS agent_credentials(
          node_id text PRIMARY KEY,
          credential_hash text NOT NULL,
          install_mode text NOT NULL DEFAULT 'UNKNOWN',
          created_at timestamptz NOT NULL DEFAULT now(),
          revoked_at timestamptz
        );

        ALTER TABLE agent_credentials
          ADD COLUMN IF NOT EXISTS install_mode text NOT NULL DEFAULT 'UNKNOWN';
        """)


async def normal_enrollment_allowed(pool):
    """NORMAL enrollment is unlocked only by a completed, unpaused pilot."""
    ready = await pool.fetchval(
        """SELECT EXISTS(
             SELECT 1
             FROM pilot_bootstrap_state
             WHERE mode='READY_FOR_EXPANSION'
               AND phase='COMPLETE'
               AND paused=false
           )"""
    )
    return bool(ready)


async def create_enrollment_token(pool, label, expires_at, authorized_mode):
    """Create a CONTROL-authorized one-time enrollment token.

    PILOT enrollment is allowed before expansion.
    NORMAL enrollment is fail-closed until a pilot reaches the persisted
    READY_FOR_EXPANSION / COMPLETE / unpaused state.
    """
    authorized_mode = _normalize_authorized_mode(authorized_mode)

    if authorized_mode == "NORMAL":
        if not await normal_enrollment_allowed(pool):
            raise ValueError(
                "NORMAL enrollment is locked until pilot is READY_FOR_EXPANSION"
            )

    token = secrets.token_urlsafe(32)

    async with pool.acquire() as c:
        await c.execute(
            """INSERT INTO enrollment_tokens(
                 token_hash,label,authorized_mode,expires_at
               )
               VALUES($1,$2,$3,$4)""",
            hash_token(token),
            label,
            authorized_mode,
            expires_at,
        )

    return token


async def enroll(pool, token, node_id):
    """Consume a CONTROL-issued token and inherit its authorized role.

    install_mode is deliberately not accepted from the enrolling client.
    """
    th = hash_token(token)
    credential = secrets.token_urlsafe(48)

    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow(
                """SELECT authorized_mode
                   FROM enrollment_tokens
                   WHERE token_hash=$1
                     AND used_at IS NULL
                     AND expires_at>now()
                   FOR UPDATE""",
                th,
            )

            if not row:
                raise ValueError("invalid/expired enrollment token")

            install_mode = _normalize_authorized_mode(row["authorized_mode"])

            existing_mode = await c.fetchval(
                """SELECT install_mode FROM agent_credentials
                   WHERE node_id=$1 AND revoked_at IS NULL
                   FOR UPDATE""",
                node_id,
            )
            if existing_mode is not None:
                existing_mode = str(existing_mode or "UNKNOWN").upper()
                if existing_mode != install_mode:
                    raise ValueError(
                        "existing node role does not match enrollment authorization"
                    )

            await c.execute(
                "UPDATE enrollment_tokens SET used_at=now() WHERE token_hash=$1",
                th,
            )

            await c.execute(
                """INSERT INTO agent_credentials(
                     node_id,credential_hash,install_mode
                   )
                   VALUES($1,$2,$3)
                   ON CONFLICT(node_id) DO UPDATE SET
                     credential_hash=EXCLUDED.credential_hash,
                     install_mode=EXCLUDED.install_mode,
                     revoked_at=NULL,
                     created_at=now()""",
                node_id,
                hash_token(credential),
                install_mode,
            )

            if install_mode == "PILOT":
                lifecycle_mode = "PILOT_BOOTSTRAP"
                lifecycle_phase = "WAITING"
                lifecycle_progress = 0
            else:
                lifecycle_mode = "NORMAL"
                lifecycle_phase = "COMPLETE"
                lifecycle_progress = 100

            await c.execute(
                """INSERT INTO pilot_bootstrap_state(
                     node_id,mode,phase,paused,progress,updated_at,
                     completed_at
                   )
                   VALUES(
                     $1,$2,$3,false,$4,now(),
                     CASE WHEN $3='COMPLETE' THEN now() ELSE NULL END
                   )
                   ON CONFLICT(node_id) DO NOTHING""",
                node_id,
                lifecycle_mode,
                lifecycle_phase,
                lifecycle_progress,
            )

    return credential


async def authenticate_agent(pool,node_id,credential):
    async with pool.acquire() as c:
        expected=await c.fetchval(
            """SELECT credential_hash FROM agent_credentials
               WHERE node_id=$1 AND revoked_at IS NULL""",
            node_id,
        )
    return bool(expected) and secrets.compare_digest(
        expected,
        hash_token(credential),
    )


async def registered_install_mode(pool,node_id):
    """CONTROL-owned enrollment role. Unknown/missing state is fail-closed."""
    mode=await pool.fetchval(
        """SELECT install_mode FROM agent_credentials
           WHERE node_id=$1 AND revoked_at IS NULL""",
        node_id,
    )
    mode=str(mode or "UNKNOWN").upper()
    return mode if mode in AUTHORIZED_INSTALL_MODES else "UNKNOWN"
