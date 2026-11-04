"""Migration 49: bounded Telegram admission state; no retention deletes."""
PUBLIC_OPERATIONS = frozenset({
    '/menu', '/ops', '/sim', '/science', '/phase', '/simstatus', '/simruns',
    '/simpassed', '/simwaiting', '/sciencestatus', '/discoveries', '/sciencehistory',
    '/sciencemining', '/sciencerejected', '/system', '/pilot', '/health', '/nodes',
    '/node', '/status', '/cleanupplan', '/controlupdatestatus', '/db', '/dbsize', '/storage',
})
_OPERATIONS_SQL = ','.join("'" + operation + "'" for operation in sorted(PUBLIC_OPERATIONS))
MIGRATION49SQL = [
    'ALTER TABLE telegram_updates ADD COLUMN actor_user_id bigint CHECK(actor_user_id>0)',
    'ALTER TABLE telegram_updates ADD COLUMN operation text CHECK(operation IN (' + _OPERATIONS_SQL + '))',
    "ALTER TABLE telegram_updates ADD COLUMN callback_digest text UNIQUE CHECK(callback_digest ~ '^[0-9a-f]{64}$')",
    "ALTER TABLE telegram_updates ADD COLUMN claim_receipt_digest text CHECK(claim_receipt_digest ~ '^[0-9a-f]{64}$')",
    '''CREATE TABLE telegram_actor_limits(
        chat_id bigint NOT NULL,user_id bigint NOT NULL CHECK(user_id>0),
        window_start timestamptz NOT NULL,attempts integer NOT NULL CHECK(attempts BETWEEN 1 AND 31),
        PRIMARY KEY(chat_id,user_id))''',
    '''CREATE TABLE telegram_ingress_audit(
        id bigserial PRIMARY KEY,update_id bigint,chat_id bigint,user_id bigint CHECK(user_id>0),
        operation text NOT NULL CHECK(operation IN ('UNKNOWN',''' + _OPERATIONS_SQL + ''')),
        decision text NOT NULL CHECK(decision IN
          ('ACCEPTED','DUPLICATE','REPLAY','STUCK','DENIED','RATE_LIMITED','CAPACITY','DONE','FAILED')),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp())''',
]
