import asyncio,time
from fastapi import FastAPI,Header,HTTPException
from .config import settings
from .bybit import linear_symbols
from .resources import capacity_score

app=FastAPI(title="Bybit Cluster Grid Coordinator")
nodes={}; instruments={}; assignments={}

def auth(token):
    if token != settings.grid_shared_token: raise HTTPException(401,"bad grid token")

@app.post("/heartbeat")
async def heartbeat(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token); nid=payload["node_id"]; payload["last_seen"]=time.time(); nodes[nid]=payload
    return {"symbols":assignments.get(nid,[])}

@app.get("/status")
async def status(x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    return {"nodes":nodes,"assignments":assignments,"instrument_count":len(instruments)}

def rebalance():
    global assignments
    alive={k:v for k,v in nodes.items() if time.time()-v["last_seen"] < settings.heartbeat_seconds*3}
    scores={k:capacity_score(v,settings.resource_cpu_limit,settings.resource_ram_limit,
                             settings.resource_disk_free_gb,settings.resource_reserve_cores) for k,v in alive.items()}
    scores={k:v for k,v in scores.items() if v>0}
    new={k:[] for k in scores}
    if not scores: assignments=new; return
    load={k:0.0 for k in scores}
    # Greedy weighted scheduling: assign next symbol to node with lowest normalized load.
    for sym in sorted(instruments):
        nid=min(scores,key=lambda n:load[n]/scores[n])
        new[nid].append(sym); load[nid]+=1
    assignments=new

@app.on_event("startup")
async def startup():
    async def loop():
        global instruments
        while True:
            try:
                xs=await linear_symbols(settings.bybit_rest_url)
                instruments={x["symbol"]:x for x in xs}; rebalance()
            except Exception as e: print("coordinator refresh error",repr(e),flush=True)
            await asyncio.sleep(settings.rebalance_seconds)
    asyncio.create_task(loop())
