from .control_state import get_control_state

KEYS=("telegram_cursor","cluster_config","active_model","scheduler_generation","leader_epoch")

async def build_replica(pool):
    state={}; generation=0
    for key in KEYS:
        row=await get_control_state(pool,key)
        if not row:continue
        v=int(row["version"]);generation=max(generation,v)
        state[key]={"_version":v,"value":row["value"]}
    # Composite generation must advance when any key changes; deterministic version vector prevents ambiguity.
    vector=";".join(f"{k}:{(state.get(k) or {}).get('_version',0)}" for k in KEYS)
    generation=sum((i+1)*int((state.get(k) or {}).get("_version",0)) for i,k in enumerate(KEYS))
    return {"version":generation,"version_vector":vector,"state":state}
