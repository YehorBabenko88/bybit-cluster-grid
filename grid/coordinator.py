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
from .update_protocol import ensure_update_schema,note_heartbeat,register_release,start_canary,promote_stable,expired_canaries
from .enrollment import ensure_enrollment_schema,enroll,authenticate_agent
from .rollout import begin_stable_rollout,note_rollout_heartbeat,expire_rollout_nodes
from .telegram_bot import telegram_loop
from .scheduler import weighted_assign,stabilize_assignments
from .control_replica_builder import build_replica
from .integrity_coordinator import handle_integrity_heartbeat
from .repair_circuit_breaker import RepairCircuitBreaker
from .repair_health import expired_repairs
from .archive_discovery_service import seed_discovery
from .pilot_state import node_accepts_live_assignments,node_live_mode
from .runtime_gate import ensure_runtime_gate,runtime_state,market_work_allowed

log=logging.getLogger("coordinator")
app=FastAPI(title="Bybit Cluster Grid Coordinator")
nodes={}; instruments={}; assignments={}
db=None
repair_breaker=RepairCircuitBreaker()

def auth(token):
    if token != settings.grid_shared_token: raise HTTPException(401,"bad grid token")

@app.post("/enroll")
async def enroll_node(payload:dict):
    try:
        credential=await enroll(db.pool,payload["enrollment_token"],payload["node_id"])
    except ValueError as e:
        raise HTTPException(401,str(e))
    return {"node_id":payload["node_id"],"credential":credential}

async def node_auth(node_id,credential,fleet_token):
    if credential and await authenticate_agent(db.pool,node_id,credential):
        return
    auth(fleet_token)

@app.post("/heartbeat")
async def heartbeat(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    nid=payload["node_id"]
    await node_auth(nid,x_node_credential,x_grid_token)
    payload["last_seen"]=time.time(); nodes[nid]=payload
    version=str(payload.get("agent_version",""))
    if version:
        await note_heartbeat(db.pool,nid,version,payload)
        await note_rollout_heartbeat(db.pool,nid,version,heartbeat=payload)
    repair_info=await handle_integrity_heartbeat(db.pool,nid,payload,repair_breaker)
    payload.update(repair_info)
    commands=await pending_commands(db.pool,nid)
    replica=await build_replica(db.pool)
    live_mode=await node_live_mode(db.pool,nid)
    fleet_state=await runtime_state(db.pool)
    market_enabled=fleet_state["state"]=="ACTIVE"
    if market_enabled and live_mode=="NORMAL":
        symbols=assignments.get(nid,[])
    elif market_enabled and live_mode=="PILOT_VALIDATING":
        preferred=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]
        symbols=[x for x in preferred if x in instruments][:5]
    else:
        symbols=[]
    return {"symbols":symbols,"commands":commands,"control_replica":replica,
            "live_assignments_enabled":bool(symbols),"live_mode":live_mode,
            "runtime_state":fleet_state["state"],"market_work_enabled":market_enabled}

@app.post("/commands/{command_id}/result")
async def post_command_result(command_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=payload.get("node_id")
    if node_id:
        await node_auth(node_id,x_node_credential,x_grid_token)
    else:
        auth(x_grid_token)
    await command_result(db.pool,command_id,bool(payload.get("ok")),payload.get("result"),payload.get("error"))
    return {"ok":True}

@app.post("/nodes/{node_id}/commands")
async def create_node_command(node_id:str,payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    allowed={"pause","resume","stop","start","restart","update","rollback","uninstall","log_tail","repair"}
    action=payload.get("action")
    if action not in allowed: raise HTTPException(400,"unsupported command")
    cid=await enqueue_command(db.pool,node_id,action,payload.get("payload"))
    return {"command_id":cid,"status":"queued"}

@app.post("/updates/releases")
async def create_release(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    await register_release(db.pool,payload["version"],payload.get("channel","canary"),
                           payload["package_url"],payload["sha256"],payload.get("metadata"))
    return {"ok":True,"version":payload["version"]}

@app.post("/updates/{version}/canary/{node_id}")
async def launch_canary(version:str,node_id:str,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    rel=await start_canary(db.pool,version,node_id,3)
    cid=await enqueue_command(db.pool,node_id,"update",rel)
    return {"command_id":cid,"version":version,"node_id":node_id,"required_health_acks":3}

@app.post("/updates/{version}/promote")
async def promote_release(version:str,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    try:
        await promote_stable(db.pool,version)
    except ValueError as e:
        raise HTTPException(409,str(e))
    alive=[nid for nid,v in nodes.items() if time.time()-v["last_seen"] < settings.heartbeat_seconds*3]
    state=await db.pool.fetchrow("SELECT canary_node FROM rollout_state WHERE version=$1",version)
    launched=await begin_stable_rollout(db.pool,version,alive,state["canary_node"])
    return {"ok":True,"version":version,"channel":"stable","launched_nodes":launched}

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
    if not scores:
        assignments={}
        return
    proposed=weighted_assign(instruments.keys(),scores,alive)
    assignments=stabilize_assignments(proposed,assignments,alive,
                                      getattr(settings,"assignment_max_churn_fraction",.10))

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
    await ensure_runtime_gate(db.pool)
    async def loop():
        global instruments,assignments
        while True:
            try:
                gate=await runtime_state(db.pool)
                if gate["state"]!="ACTIVE":
                    instruments={}
                    assignments={}
                    await asyncio.sleep(settings.rebalance_seconds)
                    continue
                xs=await linear_symbols(settings.bybit_rest_url)
                added,retired=await reconcile_instruments(db.pool,xs)
                await seed_discovery(db.pool,xs)
                instruments={x["symbol"]:x for x in xs}; rebalance()
                if added or retired:
                    log.info("instrument universe changed",extra={"event":"instrument_reconcile",
                             "component":f"added={added} retired={retired}"})
                await purge_retired(db.pool,grace_days=30)
                for failed in await expire_rollout_nodes(db.pool):
                    nid=failed["node_id"]
                    if nid in nodes and time.time()-nodes[nid]["last_seen"] < settings.heartbeat_seconds*3:
                        await enqueue_command(db.pool,nid,"rollback",{})
                for failed in await expired_repairs(db.pool):
                    nid=failed["node_id"]
                    if nid in nodes and time.time()-nodes[nid]["last_seen"] < settings.heartbeat_seconds*3:
                        await enqueue_command(db.pool,nid,"rollback",{})
                for failed in await expired_canaries(db.pool):
                    nid=failed["canary_node"]
                    # Queue rollback only when the node is currently reachable; otherwise it remains failed
                    # and can never be promoted to stable.
                    if nid in nodes and time.time()-nodes[nid]["last_seen"] < settings.heartbeat_seconds*3:
                        await enqueue_command(db.pool,nid,"rollback",{})
            except Exception:
                log.exception("coordinator refresh failed",extra={"event":"universe_refresh_failed"})
            await asyncio.sleep(settings.rebalance_seconds)
    asyncio.create_task(loop())
    asyncio.create_task(telegram_loop(db,nodes))
