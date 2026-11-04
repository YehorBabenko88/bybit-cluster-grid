async def claim_update(pool,update_id,chat_id,command,node_id):
    r=await pool.execute("""INSERT INTO telegram_updates(update_id,chat_id,command,claimed_by)
      VALUES($1,$2,$3,$4) ON CONFLICT(update_id) DO NOTHING""",
      int(update_id),str(chat_id) if chat_id is not None else None,command,node_id)
    return r.endswith(" 1")

async def complete_update(pool,update_id,error=None):
    await pool.execute("""UPDATE telegram_updates SET status=$2,completed_at=now(),error=$3
      WHERE update_id=$1 AND claim_receipt_digest IS NULL AND actor_user_id IS NULL""",int(update_id),"FAILED" if error else "DONE",error)


# New bot ingress uses this durable boundary. Legacy helpers above remain for
# non-bot callers; they do not provide sender/callback admission guarantees.
import hashlib
import secrets
from dataclasses import dataclass
from .telegram_ingress_migration import PUBLIC_OPERATIONS

ADMISSION_LOCK_KEY = 0x5447494E
MAX_CLAIMS = 100_000
MAX_AUDIT_ROWS = 100_000
MAX_ACTORS = 10_000
RATE_PER_MINUTE = 30


@dataclass(frozen=True)
class Admission:
    decision: str
    receipt: str | None = None


def callback_digest(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ValueError('invalid callback identifier')
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _bigint(value, positive=False):
    return type(value) is int and (0 < value < 2**63 if positive else -2**63 <= value < 2**63)


async def _audit(conn, update_id, chat_id, user_id, operation, decision):
    await conn.execute('''INSERT INTO telegram_ingress_audit
        (update_id,chat_id,user_id,operation,decision) VALUES($1,$2,$3,$4,$5)''',
        update_id, chat_id, user_id, operation, decision)
    return Admission(decision)


async def admit_update(pool, update_id, chat_id, user_id, operation, node_id,
                       *, callback_id=None, authorized=False):
    """Atomically bind delivery, actor and operation before any bot effects.

    Callback hashes and claims are retained indefinitely. Caps fail closed;
    operators must deliberately plan retention rather than silently forget replay
    protection. Audit reserves one terminal event for every unfinished new claim.
    """
    valid_identity = (_bigint(update_id) and update_id >= 0 and _bigint(chat_id)
                      and chat_id != 0 and _bigint(user_id, positive=True))
    update_id = update_id if _bigint(update_id) and update_id >= 0 else None
    chat_id = chat_id if _bigint(chat_id) and chat_id != 0 else None
    user_id = user_id if _bigint(user_id, positive=True) else None
    operation = operation if isinstance(operation, str) and operation in PUBLIC_OPERATIONS else 'UNKNOWN'
    digest = None
    valid_callback = True
    if callback_id is not None:
        try:
            digest = callback_digest(callback_id)
        except (ValueError, UnicodeError):
            valid_callback = False
    valid_node = isinstance(node_id, str) and 1 <= len(node_id) <= 128
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock($1)', ADMISSION_LOCK_KEY)
            counts = await conn.fetchrow('''SELECT
                (SELECT count(*) FROM telegram_ingress_audit) AS audit_count,
                (SELECT count(*) FROM telegram_updates WHERE status='CLAIMED'
                    AND claim_receipt_digest IS NOT NULL) AS pending_count,
                (SELECT count(*) FROM telegram_updates) AS claim_count,
                (SELECT count(*) FROM telegram_actor_limits) AS actor_count''')
            available = MAX_AUDIT_ROWS - counts['audit_count'] - counts['pending_count']
            if available < 1:
                return Admission('CAPACITY')
            async def decide(code):
                return await _audit(conn, update_id, chat_id, user_id, operation, code)
            # Never acknowledge an unfinished prior delivery merely because its
            # authorization was revoked or a retry presents different bindings.
            # This inspection precedes all ordinary denial/replay outcomes.
            prior = await conn.fetchrow('''SELECT chat_id,actor_user_id,operation,
                callback_digest,status,claim_receipt_digest FROM telegram_updates WHERE update_id=$1''', update_id)
            if prior and prior['status'] != 'DONE':
                return await decide('STUCK')
            callback_prior = None
            if digest is not None:
                callback_prior = await conn.fetchrow(
                    'SELECT update_id,status FROM telegram_updates WHERE callback_digest=$1', digest)
                if callback_prior and callback_prior['status'] != 'DONE':
                    return await decide('STUCK')
            if not (authorized is True and valid_identity and valid_callback and valid_node
                    and operation != 'UNKNOWN'):
                return await decide('DENIED')
            if prior:
                if prior['claim_receipt_digest'] is None:
                    return await decide('REPLAY')
                binding = (str(chat_id), user_id, operation, digest)
                stored = (prior['chat_id'], prior['actor_user_id'], prior['operation'], prior['callback_digest'])
                if binding != stored:
                    return await decide('REPLAY')
                return await decide('DUPLICATE')
            if callback_prior is not None:
                return await decide('REPLAY')
            if counts['claim_count'] >= MAX_CLAIMS or available < 2:
                return await decide('CAPACITY')
            actor_exists = await conn.fetchval(
                'SELECT 1 FROM telegram_actor_limits WHERE chat_id=$1 AND user_id=$2', chat_id, user_id)
            if not actor_exists and counts['actor_count'] >= MAX_ACTORS:
                return await decide('CAPACITY')
            attempts = await conn.fetchval('''INSERT INTO telegram_actor_limits
                (chat_id,user_id,window_start,attempts) VALUES($1,$2,clock_timestamp(),1)
                ON CONFLICT(chat_id,user_id) DO UPDATE SET
                attempts=CASE WHEN telegram_actor_limits.window_start <= clock_timestamp()-interval '60 seconds'
                    THEN 1 ELSE LEAST(telegram_actor_limits.attempts+1,31) END,
                window_start=CASE WHEN telegram_actor_limits.window_start <= clock_timestamp()-interval '60 seconds'
                    THEN clock_timestamp() ELSE telegram_actor_limits.window_start END
                RETURNING attempts''', chat_id, user_id)
            if attempts > RATE_PER_MINUTE:
                return await decide('RATE_LIMITED')
            receipt = secrets.token_hex(32)
            inserted = await conn.fetchval('''INSERT INTO telegram_updates
                (update_id,chat_id,command,claimed_by,actor_user_id,operation,callback_digest,claim_receipt_digest)
                VALUES($1,$2,$3,$4,$5,$3,$6,$7) ON CONFLICT(update_id) DO NOTHING RETURNING update_id''',
                update_id, str(chat_id), operation, node_id, user_id, digest,
                hashlib.sha256(receipt.encode('ascii')).hexdigest())
            if inserted is None:
                return await decide('STUCK')
            await decide('ACCEPTED')
            return Admission('ACCEPTED', receipt)


async def finish_update(pool, update_id, receipt, *, failed=False):
    """Only the opaque receipt issued to this claimant can complete its update."""
    if not _bigint(update_id) or update_id < 0 or not isinstance(receipt, str) or len(receipt) != 64:
        return False
    digest = hashlib.sha256(receipt.encode('utf-8')).hexdigest()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock($1)', ADMISSION_LOCK_KEY)
            row = await conn.fetchrow('''UPDATE telegram_updates SET status=$3,completed_at=clock_timestamp(),error=$4
                WHERE update_id=$1 AND claim_receipt_digest=$2 AND status='CLAIMED'
                RETURNING chat_id,actor_user_id,operation''', update_id, digest,
                'FAILED' if failed else 'DONE', 'FAILED' if failed else None)
            if row is None:
                return False
            await _audit(conn, update_id, int(row['chat_id']), row['actor_user_id'], row['operation'],
                         'FAILED' if failed else 'DONE')
            return True
