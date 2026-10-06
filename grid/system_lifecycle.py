"""Unified lifecycle controller for infrastructure, historical research and live phases."""
from __future__ import annotations
import json

PHASES=("INFRASTRUCTURE","MARKET_HISTORY_SYNC","HISTORICAL_STRATEGY_RESEARCH",
        "HISTORICAL_SCIENCE_BOOTSTRAP","GRID_IMPORT","LIVE_LEARNING","PAPER_TRADING")

PREREQUISITES={
    "MARKET_HISTORY_SYNC":{"INFRASTRUCTURE"},
    "HISTORICAL_STRATEGY_RESEARCH":{"MARKET_HISTORY_SYNC"},
    "HISTORICAL_SCIENCE_BOOTSTRAP":{"HISTORICAL_STRATEGY_RESEARCH"},
    "GRID_IMPORT":{"HISTORICAL_SCIENCE_BOOTSTRAP"},
    "LIVE_LEARNING":{"GRID_IMPORT"},
    "PAPER_TRADING":{"LIVE_LEARNING"},
}

CAPABILITIES={
    "INFRASTRUCTURE":{"collect_live":False,"train_history":False,"train_live":False,"paper":False},
    "MARKET_HISTORY_SYNC":{"collect_live":True,"train_history":False,"train_live":False,"paper":False},
    "HISTORICAL_STRATEGY_RESEARCH":{"collect_live":True,"train_history":True,"train_live":False,"paper":False},
    "HISTORICAL_SCIENCE_BOOTSTRAP":{"collect_live":True,"train_history":True,"train_live":False,"paper":False},
    "GRID_IMPORT":{"collect_live":True,"train_history":False,"train_live":False,"paper":False},
    "LIVE_LEARNING":{"collect_live":True,"train_history":False,"train_live":True,"paper":False},
    "PAPER_TRADING":{"collect_live":True,"train_history":False,"train_live":True,"paper":True},
}

async def get_phase(pool):
    row=await pool.fetchrow("SELECT phase,completed,details,updated_at FROM system_lifecycle_state WHERE singleton=true")
    if not row:return {"phase":"INFRASTRUCTURE","completed":[],"details":{}}
    completed=row["completed"]
    if isinstance(completed,str):
        try:completed=json.loads(completed)
        except ValueError:completed=[]
    details=row["details"]
    if isinstance(details,str):
        try:details=json.loads(details)
        except ValueError:details={}
    return {"phase":str(row["phase"]),"completed":list(completed or []),
            "details":dict(details or {}),"updated_at":row["updated_at"]}

async def advance_phase(pool,target,details=None):
    target=str(target).upper()
    if target not in PHASES:raise ValueError("unknown lifecycle phase")
    async with pool.acquire() as c:
        async with c.transaction():
            row=await c.fetchrow("SELECT phase,completed FROM system_lifecycle_state WHERE singleton=true FOR UPDATE")
            current=str(row["phase"]);completed=row["completed"]
            if isinstance(completed,str):completed=json.loads(completed)
            completed=list(completed or [])
            if PHASES.index(target)<PHASES.index(current):
                raise ValueError("lifecycle regression is not allowed")
            required=PREREQUISITES.get(target,set())
            known=set(completed)|{current}
            missing=required-known
            if missing:raise ValueError("missing lifecycle prerequisites: "+",".join(sorted(missing)))
            if target!=current:
                for p in PHASES[PHASES.index(current):PHASES.index(target)]:
                    if p not in completed:completed.append(p)
            await c.execute("""UPDATE system_lifecycle_state SET phase=$1,completed=$2::jsonb,
              details=$3::jsonb,updated_at=now() WHERE singleton=true""",
              target,json.dumps(completed,separators=(",",":")),
              json.dumps(details or {},sort_keys=True,separators=(",",":")))
    return await get_phase(pool)

def phase_capabilities(phase):
    return dict(CAPABILITIES.get(str(phase),CAPABILITIES["INFRASTRUCTURE"]))
