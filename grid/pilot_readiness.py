from .pilot_state import update_pilot

REQUIRED=("history_repaired","levels_complete","research_complete","import_verified","live_canary_healthy")

def readiness(details):
    missing=[k for k in REQUIRED if not bool((details or {}).get(k))]
    return {"ready":not missing,"missing":missing}

async def evaluate_pilot(pool,node_id,details):
    r=readiness(details)
    if r["ready"]:
        await update_pilot(pool,node_id,mode="READY_FOR_EXPANSION",phase="COMPLETE",
                           progress=100,paused=False,details=details)
    else:
        await update_pilot(pool,node_id,mode="PILOT_VALIDATING",phase="VERIFY",
                           details={**(details or {}),"missing_readiness":r["missing"]})
    return r
