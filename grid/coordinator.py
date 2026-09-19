import asyncio,time,logging
from fastapi import FastAPI,Header,HTTPException
from .config import settings
from .bybit import linear_symbols
from .resources import capacity_score
from .service import prepare_database,bootstrap_logging
from .instrument_lifecycle import ensure_instrument_schema,reconcile_instruments,purge_retired
from .strategy_jobs import ensure_strategy_schema,submit_job
from .strategy_plugins import ensure_plugin_schema,register_plugin,list_plugins
from .control_plane import ensure_control_schema,enqueue_command,pending_commands,command_result
from .update_protocol import ensure_update_schema
from .enrollment import ensure_enrollment_schema,enroll,authenticate_agent

log=logging.getLogger("coordinator")
app=FastAPI(title="Bybit Cluster Grid Coordinator")
nodes={}; instruments={}; assignments={}
db=None

def auth(token):
    if token != settings.grid_shared_token: raise HTTPException(401,"bad grid token")

@app.post("/heartbeat")
async def heartbeat(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    nid=payload["node_id"]; payload["last_seen"]=time.time(); nodes[nid]=payload
    commands=await pending_commands(db.pool,nid)
    return {"symbols":assignments.get(nid,[]),"commands":commands}

@app.post("/commands/{command_id}/result")
async def post_command_result(command_id:str,payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    await command_result(db.pool,command_id,bool(payload.get("ok")),payload.get("result"),payload.get("error"))
    return {"ok":True}

@app.post("/nodes/{node_id}/commands")
async def create_node_command(node_id:str,payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    allowed={"pause","resume","restart","rollback","uninstall"}
    action=payload.get("action")
    if action not in allowed: raise HTTPException(400,"unsupported command")
    cid=await enqueue_command(db.pool,node_id,action,payload.get("payload"))
    return {"command_id":cid,"status":"queued"}

@app.get("/status")
async def status(x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    return {"nodes":nodes,"assignments":assignments,"instrument_count":len(instruments)}

@app.post("/strategy/plugins")
async def upload_strategy_plugin(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    sha=await register_plugin(db.pool,payload["strategy_name"],payload["strategy_version"],
                              payload["source_code"],payload.get("metadata"))
    return {"strategy_name":payload["strategy_name"],"strategy_version":payload["strategy_version"],"sha256":sha}

@app.get("/strategy/plugins")
async def get_strategy_plugins(x_grid_token:str=Header(default="")):
    auth(x_grid_token); return {"plugins":await list_plugins(db.pool)}

@app.post("/strategy/jobs")
async def create_strategy_job(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    jid=await submit_job(db.pool,payload["strategy_name"],payload.get("strategy_version","1"),
                         payload.get("params"),payload.get("symbols"),payload.get("start_ts"),
                         payload.get("end_ts"),payload.get("priority",100))
    return {"job_id":jid,"status":"queued"}

def rebalance():
    global assignments
    alive={k:v for k,v in nodes.items() if time.time()-v["last_seen"] < settings.heartbeat_seconds*3}
    scores={k:capacity_score(v,settings.resource_cpu_limit,settings.resource_ram_limit,
                             settings.resource_disk_free_gb,settings.resource_reserve_cores) for k,v in alive.items()}
    scores={k:v for k,v in scores.items() if v>0}
    new={k:[] for k in scores}
    if not scores: assignments=new; return
    load={k:0.0 for k in scores}
    for sym in sorted(instruments):
        nid=min(scores,key=lambda n:load[n]/scores[n])
        new[nid].append(sym); load[nid]+=1
    assignments=new

@app.on_event("startup")
async def startup():
    global db
    bootstrap_logging(); db=await prepare_database()
    await ensure_instrument_schema(db.pool)
    await ensure_strategy_schema(db.pool)
    await ensure_plugin_schema(db.pool)
    await ensure_control_schema(db.pool)
    await ensure_update_schema(db.pool)
    await ensure_enrollment_schema(db.pool)
    async def loop():
        global instruments
        while True:
            try:
                xs=await linear_symbols(settings.bybit_rest_url)
                added,retired=await reconcile_instruments(db.pool,xs)
                instruments={x["symbol"]:x for x in xs}; rebalance()
                if added or retired:
                    log.info("instrument universe changed",extra={"event":"instrument_reconcile",
                             "component":f"added={added} retired={retired}"})
                await purge_retired(db.pool,grace_days=30)
            except Exception:
                log.exception("coordinator refresh failed",extra={"event":"universe_refresh_failed"})
            await asyncio.sleep(settings.rebalance_seconds)
    asyncio.create_task(loop())
