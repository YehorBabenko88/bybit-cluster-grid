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
    row = await get_control_state(pool, "telegram_cursor")

    if row:
        value = _json_object(row["value"])
        current = int(value.get("next_update_id", 0))
    else:
        current = 0

    next_update_id = int(next_update_id)

    if next_update_id <= current:
        return current

    await put_control_state(
        pool,
        "telegram_cursor",
        {"next_update_id": next_update_id},
        node_id,
    )

    return next_update_id
