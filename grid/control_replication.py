from .control_state import get_control_state,put_control_state

CRITICAL_KEYS=("telegram_cursor","cluster_config","active_model","scheduler_generation","leader_epoch")

async def sync_control_to_local(pool,journal):
    local=journal.load(); merged=dict(local["state"]); maxver=local["version"]
    for key in CRITICAL_KEYS:
        row=await get_control_state(pool,key)
        if not row:continue
        # DB versions are per-key; retain them inside state and advance journal generation monotonically.
        old=(merged.get(key) or {}).get("_version",0)
        if int(row["version"])>int(old):
            merged[key]={"_version":int(row["version"]),"value":row["value"]}
            maxver+=1
    journal.apply(maxver,merged)
    return journal.load()

async def telegram_cursor(pool,journal=None):
    try:
        row=await get_control_state(pool,"telegram_cursor")
        if row:return int((row["value"] or {}).get("next_update_id",0))
    except Exception:
        if journal:
            x=journal.load()["state"].get("telegram_cursor") or {}
            return int((x.get("value") or {}).get("next_update_id",0))
        raise
    return 0

async def commit_telegram_cursor(pool,node_id,next_update_id):
    # Monotonic in value as well as state version.
    row=await get_control_state(pool,"telegram_cursor")
    current=int((row["value"] or {}).get("next_update_id",0)) if row else 0
    if int(next_update_id)<=current:return current
    await put_control_state(pool,"telegram_cursor",{"next_update_id":int(next_update_id)},node_id)
    return int(next_update_id)
