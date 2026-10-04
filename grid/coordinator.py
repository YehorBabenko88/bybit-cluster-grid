import asyncio,time,logging,secrets
from fastapi import FastAPI,Header,HTTPException,Request
from .config import settings
from .bybit import linear_symbols
from .resources import capacity_score,snapshot as resource_snapshot
from .service import prepare_database,bootstrap_logging
from .instrument_lifecycle import ensure_instrument_schema,reconcile_instruments,purge_retired
from .strategy_jobs import ensure_strategy_schema,submit_job
from .strategy_plugins import ensure_plugin_schema,register_plugin,list_plugins
from .control_plane import ensure_control_schema,enqueue_command,pending_commands,command_result
from .update_protocol import ensure_update_schema,note_heartbeat,register_release,start_canary,promote_stable,expired_canaries
from .enrollment import ensure_enrollment_schema,enroll,authenticate_agent,registered_install_mode
from .rollout import begin_stable_rollout,note_rollout_heartbeat,expire_rollout_nodes
from .telegram_bot import telegram_loop
from .scheduler import weighted_assign,stabilize_assignments
from .control_replica_builder import build_replica
from .integrity_coordinator import handle_integrity_heartbeat
from .repair_circuit_breaker import RepairCircuitBreaker
from .repair_health import expired_repairs
from .archive_discovery_service import seed_discovery
from .pilot_state import node_accepts_live_assignments,node_live_mode
from .live_assignment_policy import guarded_live_symbols
from .runtime_gate import ensure_runtime_gate,runtime_state,market_work_allowed
from .fleet_control import reconcile_fleet_operation
from .storage import Storage
from .ml_microstructure_lifecycle import MicrostructureMLLifecycle,parse_horizons
from .strattester_bridge import create_research_run,enqueue_research_shards,reconcile_research_runs,claim_assigned_strattester_job,renew_strattester_job,complete_strattester_job
from .ml_dispatcher import MLDispatcher
from .ml_orchestrator_service import MLOrchestratorService
from .ml_retry import fail_or_retry
from .archive_compute_queue import seed_archive_compute_jobs,claim_archive_compute_job,renew_archive_compute_job,fail_archive_compute_job,accept_archive_compute_result,recover_archive_compute_jobs
from .operational_gc import cleanup_operational_state
from .node_lifecycle import record_node_seen,reconcile_node_lifecycle,node_may_compute

log=logging.getLogger("coordinator")
app=FastAPI(title="Bybit Cluster Grid Coordinator")
nodes={}; instruments={}; assignments={}
db=None
ingest_storage=None
background_tasks=[]
repair_breaker=RepairCircuitBreaker()
micro_ml_lifecycle=None
ml_orchestrator=None


def constant_time_equal(left,right):
    """Compare authentication tokens without leaking early string mismatch timing."""
    return secrets.compare_digest(str(left or ""),str(right or ""))


def auth(token):
    if not constant_time_equal(token,settings.grid_shared_token):
        raise HTTPException(401,"bad grid token")

@app.post("/enroll")
async def enroll_node(payload:dict):
    try:
        credential=await enroll(
            db.pool,
            payload["enrollment_token"],
            payload["node_id"],
        )
    except ValueError as e:
        raise HTTPException(401,str(e))
    install_mode=await registered_install_mode(db.pool,payload["node_id"])
    return {"node_id":payload["node_id"],"credential":credential,"install_mode":install_mode}

async def node_auth(node_id,credential,fleet_token):
    if credential and await authenticate_agent(db.pool,node_id,credential):
        return
    auth(fleet_token)

@app.post("/heartbeat")
async def heartbeat(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    nid=payload["node_id"]
    await node_auth(nid,x_node_credential,x_grid_token)
    lifecycle=await record_node_seen(db.pool,nid)
    if lifecycle=="DECOMMISSIONED":
        raise HTTPException(409,"node decommissioned; re-enrollment required")
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
    install_mode=await registered_install_mode(db.pool,nid)
    fleet_state=await runtime_state(db.pool)
    market_enabled=fleet_state["state"]=="ACTIVE"

    symbols=guarded_live_symbols(
        market_enabled=market_enabled,
        install_mode=install_mode,
        live_mode=live_mode,
        node_assignments=assignments.get(nid,[]),
        instrument_symbols=instruments,
    )
    # High-rate microstructure capture remains pilot-only until the volatility
    # selector is implemented; this prevents accidental fleet-wide 250 ms capture.
    micro_symbols=sorted(symbols)[:max(0,int(settings.micro_max_symbols_per_node))] if install_mode=="PILOT" else []
    return {"symbols":symbols,"micro_symbols":micro_symbols,"commands":commands,"control_replica":replica,
            "live_assignments_enabled":bool(symbols),"live_mode":live_mode,
            "install_mode":install_mode,
            "runtime_state":fleet_state["state"],"market_work_enabled":market_enabled}

@app.post("/compute/archive/claim")
async def claim_archive_compute(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""))
    if not node_id: raise HTTPException(400,"node_id required")
    await node_auth(node_id,x_node_credential,x_grid_token)
    if not await node_may_compute(db.pool,node_id):
        raise HTTPException(409,"node lifecycle blocks compute")
    info=nodes.get(node_id) or {}
    if not bool((info.get("compute_capabilities") or {}).get("archive")):
        raise HTTPException(409,"node does not advertise archive capability")
    job=await claim_archive_compute_job(db.pool,node_id,int(payload.get("lease_seconds",300)))
    if not job:return {"job":None}
    out=dict(job)
    for k,v in list(out.items()):
        if v is not None and k in ("id","archive_date","lease_until","created_at","updated_at"):out[k]=str(v)
    return {"job":out}

@app.post("/compute/archive/{job_id}/renew")
async def renew_archive_compute(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""));await node_auth(node_id,x_node_credential,x_grid_token)
    ok=await renew_archive_compute_job(db.pool,job_id,node_id,int(payload["lease_generation"]),
                                       int(payload.get("lease_seconds",300)))
    if not ok:raise HTTPException(409,"lease lost")
    return {"ok":True}

@app.post("/compute/archive/{job_id}/fail")
async def fail_archive_compute(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""));await node_auth(node_id,x_node_credential,x_grid_token)
    ok=await fail_archive_compute_job(db.pool,job_id,node_id,int(payload["lease_generation"]),
                                      str(payload.get("error","archive compute failed")))
    if not ok:raise HTTPException(409,"lease lost")
    return {"ok":True}

@app.post("/compute/archive/{job_id}/result")
async def complete_archive_compute(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""));await node_auth(node_id,x_node_credential,x_grid_token)
    try:
        ok=await accept_archive_compute_result(db.pool,job_id,node_id,int(payload["lease_generation"]),
                                               dict(payload.get("manifest") or {}))
    except ValueError as exc:
        raise HTTPException(409,str(exc))
    if not ok:raise HTTPException(409,"lease lost")
    return {"ok":True}

@app.post("/research/runs")
async def create_distributed_research(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    required=("kind","dataset_id","dataset_hash","config","strattester_version","shards")
    missing=[k for k in required if k not in payload]
    if missing: raise HTTPException(400,"missing: "+",".join(missing))
    try:
        run_id=await create_research_run(
            db.pool,kind=payload["kind"],dataset_id=payload.get("dataset_id"),
            dataset_hash=payload["dataset_hash"],config=payload.get("config") or {},
            strattester_version=payload["strattester_version"],shards=payload.get("shards") or [])
        queued=await enqueue_research_shards(db.pool,run_id)
    except ValueError as exc:
        raise HTTPException(409,str(exc))
    return {"run_id":run_id,"queued_shards":queued}

@app.get("/research/runs/{run_id}")
async def get_distributed_research(run_id:str,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    run=await db.pool.fetchrow("SELECT * FROM research_runs WHERE id=$1",run_id)
    if not run: raise HTTPException(404,"research run not found")
    shards=await db.pool.fetch("""SELECT id,job_type,shard_key,status,result_hash,created_at,finished_at
      FROM research_shards WHERE run_id=$1 ORDER BY job_type,shard_key""",run_id)
    def serial(row):
        out=dict(row)
        for k,v in list(out.items()):
            if v is not None and k in ("id","created_at","finished_at","dataset_id"): out[k]=str(v)
        return out
    return {"run":serial(run),"shards":[serial(x) for x in shards]}

@app.post("/compute/strattester/claim")
async def claim_strattester_compute(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""))
    if not node_id: raise HTTPException(400,"node_id required")
    await node_auth(node_id,x_node_credential,x_grid_token)
    if not await node_may_compute(db.pool,node_id):
        raise HTTPException(409,"node lifecycle blocks compute")
    job=await claim_assigned_strattester_job(db.pool,node_id,int(payload.get("lease_seconds",120)))
    if not job:return {"job":None}
    out=dict(job)
    for key in ("id","created_at","started_at","finished_at","lease_until","dataset_cutoff","not_before"):
        if out.get(key) is not None: out[key]=str(out[key])
    return {"job":out}

@app.post("/compute/strattester/{job_id}/renew")
async def renew_strattester_compute(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""))
    if not node_id: raise HTTPException(400,"node_id required")
    await node_auth(node_id,x_node_credential,x_grid_token)
    ok=await renew_strattester_job(db.pool,job_id,node_id,int(payload["lease_generation"]),
                                   int(payload.get("lease_seconds",120)))
    if not ok: raise HTTPException(409,"lease lost")
    return {"ok":True}

@app.post("/compute/strattester/{job_id}/fail")
async def fail_strattester_compute(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""))
    if not node_id: raise HTTPException(400,"node_id required")
    await node_auth(node_id,x_node_credential,x_grid_token)
    kind=str(payload.get("kind","retryable"))
    if kind not in ("retryable","permanent"): raise HTTPException(400,"invalid failure kind")
    state=await fail_or_retry(db.pool,job_id,node_id,int(payload["lease_generation"]),
                              str(payload.get("error","remote Strattester failure")),kind)
    if state=="stale": raise HTTPException(409,"lease lost")
    await db.pool.execute("DELETE FROM ml_resource_reservations WHERE job_id=$1",job_id)
    return {"ok":True,"state":state}

@app.post("/compute/strattester/{job_id}/result")
async def complete_strattester_compute(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""))
    if not node_id: raise HTTPException(400,"node_id required")
    await node_auth(node_id,x_node_credential,x_grid_token)
    manifest=payload.get("manifest")
    if not isinstance(manifest,dict): raise HTTPException(400,"manifest required")
    try:
        ok=await complete_strattester_job(db.pool,job_id,node_id,int(payload["lease_generation"]),manifest)
    except ValueError as exc:
        raise HTTPException(409,str(exc))
    if not ok: raise HTTPException(409,"lease lost")
    return {"ok":True}

@app.post("/commands/{command_id}/result")
async def post_command_result(command_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=payload.get("node_id")
    if node_id:
        await node_auth(node_id,x_node_credential,x_grid_token)
    else:
        auth(x_grid_token)
    await command_result(
        db.pool,
        command_id,
        bool(payload.get("ok")),
        payload.get("result"),
        payload.get("error"),
    )
    # Fleet STOP/RESUME completion is driven by durable command ACKs.
    # Reconcile immediately after every command result so the global
    # runtime gate cannot remain indefinitely in STOPPING/RESUMING.
    await reconcile_fleet_operation(db.pool)
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


@app.post("/ingest/minute")
async def ingest_minute(request:Request,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default=""),x_node_id:str=Header(default="")):
    global ingest_storage
    if not constant_time_equal(x_grid_token,settings.grid_shared_token):
        raise HTTPException(403)
    payload=await request.json()
    if not x_node_id or not await authenticate_agent(db.pool,x_node_id,x_node_credential):
        raise HTTPException(403)
    gate=await runtime_state(db.pool)
    if gate["state"]!="ACTIVE":
        raise HTTPException(423,"market ingestion locked")
    if ingest_storage is None:
        raise HTTPException(503,"ingestion unavailable")
    await ingest_storage._save_direct(payload)
    return {"ok":True}

@app.post("/ingest/event")
async def ingest_event(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default=""),x_node_id:str=Header(default="")):
    if not constant_time_equal(x_grid_token,settings.grid_shared_token):
        raise HTTPException(403)
    if not x_node_id or not await authenticate_agent(db.pool,x_node_id,x_node_credential):
        raise HTTPException(403)
    gate=await runtime_state(db.pool)
    if gate["state"]!="ACTIVE":
        raise HTTPException(423,"market ingestion locked")
    symbol=str(payload.get("symbol","")).strip()
    event_type=str(payload.get("event_type","")).strip()
    event_ts=payload.get("event_ts")
    event_payload=payload.get("payload")
    if not symbol or not event_type or event_ts is None or not isinstance(event_payload,dict):
        raise HTTPException(400,"invalid micro-event payload")
    await db.insert_event(symbol,int(event_ts),event_type,event_payload)
    return {"ok":True}


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
    global db, ingest_storage, background_tasks, micro_ml_lifecycle, ml_orchestrator
    bootstrap_logging()
    log.info(
        "coordinator startup",
        extra={"event": "coordinator_startup", "component": "coordinator"},
    )
    db=await prepare_database()
    await ensure_instrument_schema(db.pool)
    await ensure_strategy_schema(db.pool)
    await ensure_plugin_schema(db.pool)
    await ensure_control_schema(db.pool)
    await ensure_update_schema(db.pool)
    await ensure_enrollment_schema(db.pool)
    await ensure_runtime_gate(db.pool)
    ingest_storage=Storage()
    ingest_storage.pool=db.pool
    ingest_storage.derived=__import__('grid.derived_pipeline',fromlist=['DerivedPipeline']).DerivedPipeline(db.pool)
    await ingest_storage.derived.start()
    async def loop():
        global instruments,assignments
        while True:
            try:
                # Recovery path for a crash/restart occurring after an agent
                # persisted its command result but before the request-path
                # reconcile completed.
                await reconcile_fleet_operation(db.pool)
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
    async def research_reconciler_loop():
        while True:
            try:
                await reconcile_research_runs(db.pool)
            except Exception:
                log.exception("research DAG reconcile failed",extra={"event":"research_reconcile_failed"})
            await asyncio.sleep(5)

    async def archive_compute_reconciler_loop():
        while True:
            try:
                await recover_archive_compute_jobs(db.pool)
                await seed_archive_compute_jobs(db.pool)
            except Exception:
                log.exception("archive compute reconcile failed",extra={"event":"archive_compute_reconcile_failed"})
            await asyncio.sleep(10)

    async def node_lifecycle_loop():
        while True:
            try:
                await reconcile_node_lifecycle(db.pool,settings.node_offline_seconds,
                    settings.node_quarantine_hours,settings.node_decommission_days)
            except Exception:
                log.exception("node lifecycle reconcile failed",extra={"event":"node_lifecycle_failed"})
            await asyncio.sleep(30)

    async def operational_gc_loop():
        while True:
            try:
                await cleanup_operational_state(db.pool,settings.operational_state_retention_days)
            except Exception:
                log.exception("operational gc loop failed",extra={"event":"operational_gc_loop_failed"})
            await asyncio.sleep(max(3600,int(settings.maintenance_interval_minutes)*60))

    async def compute_nodes():
        cutoff=time.time()-settings.heartbeat_seconds*3
        return {nid:dict(v) for nid,v in nodes.items() if v.get("last_seen",0)>=cutoff}

    async def ml_health():
        s=resource_snapshot()
        started=time.perf_counter()
        try:
            await db.pool.fetchval("SELECT 1")
            latency=(time.perf_counter()-started)*1000
        except Exception:
            latency=9999.0
        live=[v for v in nodes.values() if time.time()-v.get("last_seen",0)<settings.heartbeat_seconds*3]
        queue_ratio=max([float(v.get("db_queue_ratio",0) or 0) for v in live] or [0.0])
        return {"cpu_pct":float(s["cpu_pct"]),"ram_pct":float(s["ram_pct"]),
                "disk_free_gb":float(s["disk_free"])/(1024**3),
                "db_latency_ms":latency,"db_queue_ratio":queue_ratio}

    dispatcher=MLDispatcher(db.pool,compute_nodes)
    ml_orchestrator=MLOrchestratorService(db.pool,dispatcher,ml_health,interval=5)

    background_tasks = [
        asyncio.create_task(loop()),
        asyncio.create_task(telegram_loop(db,nodes)),
        asyncio.create_task(ml_orchestrator.run()),
        asyncio.create_task(research_reconciler_loop()),
        asyncio.create_task(archive_compute_reconciler_loop()),
        asyncio.create_task(operational_gc_loop()),
        asyncio.create_task(node_lifecycle_loop()),
    ]
    if settings.micro_ml_lifecycle_enabled:
        micro_ml_lifecycle=MicrostructureMLLifecycle(
            db.pool,parse_horizons(settings.micro_ml_horizons_seconds),
            settings.micro_ml_lifecycle_seconds)
        background_tasks.append(asyncio.create_task(micro_ml_lifecycle.run()))

@app.on_event("shutdown")
async def shutdown():
    global ingest_storage, background_tasks, micro_ml_lifecycle, ml_orchestrator

    if micro_ml_lifecycle is not None:
        micro_ml_lifecycle.stop()
    if ml_orchestrator is not None:
        ml_orchestrator.stop()
    tasks = list(background_tasks)
    background_tasks = []

    for task in tasks:
        task.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    ingest_storage = None
    micro_ml_lifecycle = None
    ml_orchestrator = None
