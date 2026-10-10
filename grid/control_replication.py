import json

from .control_state import get_control_state, put_control_state

CRITICAL_KEYS = (
    "telegram_cursor",
    "cluster_config",
    "active_model",
    "scheduler_generation",
    "leader_epoch",
)


def _json_object(value):
    """Normalize asyncpg json/jsonb values to a Python dict."""
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

        return decoded if isinstance(decoded, dict) else {}

    return {}


async def sync_control_to_local(pool, journal):
    local = journal.load()
    merged = dict(local["state"])
    maxver = local["version"]

    for key in CRITICAL_KEYS:
        row = await get_control_state(pool, key)
        if not row:
            continue

        old = (merged.get(key) or {}).get("_version", 0)

        if int(row["version"]) > int(old):
            merged[key] = {
                "_version": int(row["version"]),
                "value": _json_object(row["value"]),
            }
            maxver += 1

    journal.apply(maxver, merged)
    return journal.load()


async def telegram_cursor(pool, journal=None):
    try:
        row = await get_control_state(pool, "telegram_cursor")

        if row:
            value = _json_object(row["value"])
            return int(value.get("next_update_id", 0))

    except Exception:
        if journal:
            item = journal.load()["state"].get("telegram_cursor") or {}
            value = _json_object(item.get("value"))
            return int(value.get("next_update_id", 0))
        raise

    return 0


async def commit_telegram_cursor(pool, node_id, next_update_id):
    """Advance the shared Telegram cursor monotonically in one DB statement."""
    next_update_id = int(next_update_id)
    if next_update_id < 0:
        raise ValueError("negative Telegram cursor")
    row = await pool.fetchrow("""
        INSERT INTO replicated_control_state (state_key,value,updated_by)
        VALUES ('telegram_cursor',jsonb_build_object('next_update_id',$1::bigint),$2)
        ON CONFLICT (state_key) DO UPDATE
        SET value=EXCLUDED.value,
            version=replicated_control_state.version+1,
            updated_at=now(),updated_by=EXCLUDED.updated_by
        WHERE COALESCE(
            CASE WHEN (replicated_control_state.value->>'next_update_id') ~ '^[0-9]+$'
            THEN (replicated_control_state.value->>'next_update_id')::bigint
            ELSE 0 END,0) < $1::bigint
        RETURNING (value->>'next_update_id')::bigint AS next_update_id
    """,next_update_id,node_id)
    if row:
        return int(row["next_update_id"])
    current = await telegram_cursor(pool)
    return max(current,next_update_id) if current == next_update_id else current
