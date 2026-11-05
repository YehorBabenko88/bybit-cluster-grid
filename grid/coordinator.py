import asyncio,time,logging,secrets,hashlib,tempfile,os,pathlib,subprocess,json,configparser,re,stat,threading
from fastapi import FastAPI,Header,HTTPException,Request
from fastapi.responses import JSONResponse
from .coordination import coordinator_authority, floating_leader_guard
from .floating_leader import FloatingLeader
from .config import settings
from .bybit import linear_symbols
from .resources import capacity_score,node_accepts_work
from .service import prepare_database,bootstrap_logging
from .instrument_lifecycle import ensure_instrument_schema,reconcile_instruments,purge_retired
from .strategy_jobs import ensure_strategy_schema,submit_job
from .strategy_plugins import ensure_plugin_schema,register_plugin,list_plugins
from .control_plane import ensure_control_schema,enqueue_command,pending_commands,command_result
from .update_protocol import ensure_update_schema,note_heartbeat,register_release,start_canary,promote_stable,expired_canaries
from .enrollment import ensure_enrollment_schema,enroll,authenticate_agent,registered_install_mode,create_enrollment_token
from .rollout import begin_stable_rollout,note_rollout_heartbeat,expire_rollout_nodes
from .telegram_bot import telegram_loop
from .scheduler import weighted_assign,stabilize_assignments
from .control_replica_builder import build_replica
from .integrity_coordinator import handle_integrity_heartbeat
from .repair_circuit_breaker import RepairCircuitBreaker
from .repair_health import expired_repairs
from .archive_discovery_service import seed_discovery
from .pilot_state import node_accepts_live_assignments,node_live_mode
from .live_assignment_policy import guarded_live_symbols,pilot_universe
from .runtime_gate import ensure_runtime_gate,runtime_state,market_work_allowed
from .fleet_control import reconcile_fleet_operation
from .storage import Storage
from .retention import retention_scheduler, ensure_retention_schema
from .maintenance import maintenance_scheduler
from .ml_artifact_store import LocalArtifactStore
from .ml_transport import claim as ml_claim,renew as ml_renew,dataset_bundle as ml_dataset_bundle,dataset_page as ml_dataset_page,publish_artifact as ml_publish_artifact,register_saved_artifact as ml_register_saved_artifact,finalize_model as ml_finalize_model
from .ml_dispatcher import MLDispatcher
from .data_first_jobs import enqueue as enqueue_data_first,publish as publish_data_first
from .ml_transport import claim_data_first,train_lease_valid as ml_train_lease_valid
from .ml_orchestrator_service import MLOrchestratorService
from .resources import snapshot as resource_snapshot
from .asyncio_guard import install_asyncio_exception_filter
from .disk_guard import DiskWatermarks,disk_state,live_collection_allowed
from .tailscale_provisioning import create_one_time_auth_key,TailscaleProvisioningError
from .scientific_service import ScientificResearchService
from .historical_science_import import import_historical_science
from .system_lifecycle import get_phase,advance_phase,phase_capabilities,PHASES

log=logging.getLogger("coordinator")
app=FastAPI(title="Bybit Cluster Grid Coordinator")
nodes={}; instruments={}; assignments={}
db=None
ingest_storage=None
background_tasks=[]
repair_breaker=RepairCircuitBreaker()
ml_orchestrator=None
scientific_service=None
coordination_authority=None
control_leader=None
control_task=None
_MODULE_SOURCE_ROOT=pathlib.Path(__file__).resolve().parents[1]
_MODULE_HEALTH_TIMEOUT=1.0
_owned_module_binding=None
_owned_module_source_admission=None
_OWNED_MODULE_ENV=('UNIFIED_MODULE_ID','UNIFIED_MODULE_VERSION','UNIFIED_RELEASE_ID',
                   'UNIFIED_INSTANCE_TOKEN','UNIFIED_SOURCE_COMMIT')



@app.middleware('http')
async def coordinated_request_guard(request, call_next):
    if (getattr(settings, 'grid_coordination_mode', 'legacy') == 'consul'
            and request.url.path not in ('/health', '/ready')):
        if control_leader is None or not control_leader.ready or control_leader.requires_fencing:
            return JSONResponse({'reason': 'COORDINATION_NOT_READY'}, status_code=503)
        try:
            await floating_leader_guard(control_leader)()
        except Exception:
            return JSONResponse({'reason': 'COORDINATION_NOT_READY'}, status_code=503)
    return await call_next(request)


@app.get('/ready')
async def control_readiness():
    if db is None or getattr(db, 'pool', None) is None:
        raise HTTPException(503, 'database not ready')
    mode = getattr(settings, 'grid_coordination_mode', 'legacy')
    if mode == 'consul':
        if control_leader is None or not control_leader.ready or control_leader.requires_fencing:
            raise HTTPException(503, 'DCS-backed control is not ready')
        try:await floating_leader_guard(control_leader)()
        except Exception:raise HTTPException(503, 'DCS-backed control is not ready')
    return {'ready': True, 'coordination_mode': mode,
            'physical_ha_qualified': False, 'legacy_single_primary': mode == 'legacy'}


def _owned_module_identity():
    values=tuple(os.environ.get(key,'') for key in _OWNED_MODULE_ENV)
    module,version,release,token,source=values
    if (module!='grid' or len(version)>128
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]{1,40})?',version)
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',release)
            or not re.fullmatch(r'[a-f0-9]{64}',token)
            or not re.fullmatch(r'[a-f0-9]{40}',source)):
        return None
    return values


def _safe_owned_git_config(root):
    # Validate local metadata before Git can read include/filter/fsmonitor hooks.
    metadata=root/'.git'
    for path in (root,*root.parents):
        info=path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:return False
    for relative in ('objects/info/alternates','objects/info/http-alternates','info/attributes'):
        if os.path.lexists(metadata/relative):return False
    for relative in ('objects','objects/info','info'):
        path=metadata/relative
        if os.path.lexists(path):
            info=path.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:return False
    config=metadata/'config'
    for path in (metadata,config):
        info=path.lstat()
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400)):
            return False
    if not metadata.is_dir() or not config.is_file() or (metadata/'commondir').exists():
        return False
    examined=0
    deadline=time.monotonic()+1
    for directory,dirs,files in os.walk(metadata/'objects',followlinks=False):
        for name in dirs+files:
            examined+=1
            if examined>200000 or time.monotonic()>deadline:return False
            info=(pathlib.Path(directory)/name).lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:return False
    with config.open('rb') as stream:raw=stream.read(65537)
    if len(raw)>65536:return False
    parser=configparser.RawConfigParser(strict=False)
    parser.read_string(raw.decode('utf-8-sig'))
    if parser.defaults():return False
    core={'repositoryformatversion','filemode','bare','logallrefupdates','ignorecase',
          'precomposeunicode','symlinks','protectntfs','protecthfs','longpaths',
          'hookspath','attributesfile','fsmonitor','untrackedcache','autocrlf'}
    nulls={os.devnull.casefold(),'/dev/null','nul'}
    for section in parser.sections():
        name=section.casefold()
        if name=='core':allowed=core
        elif re.fullmatch(r'remote "[^"\r\n]{1,128}"',name):allowed={'url','fetch','tagopt','pushurl'}
        elif re.fullmatch(r'branch "[^"\r\n]{1,256}"',name):allowed={'remote','merge','rebase'}
        elif name=='user':allowed={'name','email','signingkey'}
        else:return False
        for key,value in parser.items(section):
            if key not in allowed:return False
            value=value.strip().strip('"').casefold()
            if key in ('hookspath','attributesfile') and value not in nulls:return False
            if key in ('fsmonitor','bare','autocrlf') and value not in ('false','0','off','no'):return False
            if key=='repositoryformatversion' and value!='0':return False
    return True


def _owned_startup_scope(admission,expected,*,verify_git=False):
    """Live in-process source scope; no CLI/environment authorization."""
    if isinstance(admission,dict) or not all(callable(getattr(admission,name,None)) for name in ('require_current','source_scope')):
        raise ValueError('Owned module source binding unavailable')
    if admission.require_current() is not True or re.fullmatch('[a-f0-9]{40}',expected) is None:
        raise ValueError('Owned module source binding unavailable')
    root=_MODULE_SOURCE_ROOT.absolute()
    scoped=admission.source_scope('grid',root,expected)
    if (not isinstance(scoped,pathlib.Path) or not scoped.is_absolute()
            or any(c in str(scoped) for c in ('*','?','[',']','\n','\r','\0'))
            or scoped!=root or scoped.resolve(strict=True)!=root):
        raise ValueError('Owned module source binding unavailable')
    if admission.require_current() is not True:raise ValueError('Owned module source binding unavailable')
    if not verify_git:return root
    executable=pathlib.Path(admission.git_executable);digest=admission.git_sha256
    if not executable.is_absolute() or executable.resolve(strict=True)!=executable or re.fullmatch('[a-f0-9]{64}',digest) is None:
        raise ValueError('Owned module Git pin unavailable')
    info=executable.lstat()
    if (not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400
            or not 0<info.st_size<=64*1024*1024
            or not secrets.compare_digest(hashlib.sha256(executable.read_bytes()).hexdigest(),digest)):
        raise ValueError('Owned module Git pin unavailable')
    if admission.require_current() is not True:raise ValueError('Owned module source binding unavailable')
    return root,executable


def _owned_source_is_clean(expected,*,owner_admitted_root=None,startup_admission=None):
    root=_MODULE_SOURCE_ROOT.absolute()
    try:
        executable='git'
        if startup_admission is not None:
            if owner_admitted_root is not None:return False
            owner_admitted_root,executable=_owned_startup_scope(startup_admission,expected,verify_git=True)
        if owner_admitted_root is not None:
            # Only an explicitly admitted exact canonical checkout; no parent,
            # wildcard, alias or environment-derived trust exception.
            if not isinstance(owner_admitted_root,(str,pathlib.Path)):return False
            admitted=str(owner_admitted_root)
            if any(c in admitted for c in ('*','?','[',']','\n','\r','\0')):return False
            candidate=pathlib.Path(admitted)
            if (not candidate.is_absolute() or '..' in candidate.parts or admitted!=str(root)
                    or str(root.resolve(strict=True))!=str(root)):return False
        if not _safe_owned_git_config(root):return False
        # Keep proxy/CA environment intact; Git-specific redirects and injected
        # configuration cannot choose a different checkout or executable helper.
        env={key:value for key,value in os.environ.items() if not key.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0',GIT_NO_REPLACE_OBJECTS='1',GIT_NO_LAZY_FETCH='1')
        command=[str(executable),'--no-replace-objects','--no-pager','-c','core.fsmonitor=false',
                 '-c','core.hooksPath='+os.devnull,'-c','core.attributesFile='+os.devnull,
                 '-c','core.untrackedCache=false','-c','submodule.recurse=false','-C',str(root)]
        if owner_admitted_root is not None:command[3:3]=['-c','safe.directory=','-c','safe.directory='+str(root)]
        started=time.monotonic()
        def git(*args,limit=2*1024*1024):
            # Timer kills a blocked child on both Windows and Linux; bounded
            # pipe reads prevent a hostile tree/status from exhausting memory.
            if startup_admission is not None:
                if _owned_startup_scope(startup_admission,expected,verify_git=True)!=(root,executable):raise ValueError('Owned module source binding unavailable')
            child=subprocess.Popen(command+list(args),env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            timer=threading.Timer(1,child.kill)
            timer.start()
            try:
                output=child.stdout.read(limit+1)
                if len(output)>limit:
                    child.kill()
                    raise ValueError('Git output bound exceeded')
                if child.wait(timeout=1)!=0:raise ValueError('Git command rejected')
                return output
            finally:
                timer.cancel()
                if child.poll() is None:child.kill()
                child.wait(timeout=1)
                child.stdout.close()
        if pathlib.Path(os.fsdecode(git('rev-parse','--show-toplevel')).strip()).resolve()!=root:return False
        if git('rev-parse','HEAD').decode('ascii').strip()!=expected:return False
        tree=git('ls-tree','-r','-z','--full-tree',expected,limit=8*1024*1024)
        total=0
        entries=tree.split(b'\0')
        if len(entries)>20001:return False
        for entry in entries:
            if not entry:continue
            metadata,name=entry.split(b'\t',1)
            mode,kind,oid=metadata.split(b' ')
            if mode not in (b'100644',b'100755') or kind!=b'blob' or not re.fullmatch(b'[a-f0-9]{40}',oid):return False
            relative=pathlib.PurePosixPath(os.fsdecode(name))
            if relative.is_absolute() or any(part in ('..','.git') or '\\' in part or ':' in part for part in relative.parts):return False
            path=root.joinpath(*relative.parts)
            for ancestor in (path,*path.parents):
                if ancestor==root:break
                info=ancestor.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:return False
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size>16*1024*1024:return False
            total+=info.st_size
            if total>256*1024*1024 or time.monotonic()-started>3:return False
            # Git blob IDs hash the raw bytes with a length prefix, independently
            # of index flags, attributes and worktree conversion/filter rules.
            digest=hashlib.sha1(b'blob '+str(info.st_size).encode('ascii')+b'\0')
            with path.open('rb') as stream:
                remaining=info.st_size
                while remaining:
                    block=stream.read(min(65536,remaining))
                    if not block:return False
                    digest.update(block);remaining-=len(block)
                if stream.read(1):return False
            if digest.hexdigest().encode('ascii')!=oid:return False
        clean=git('status','--porcelain','--untracked-files=all','--ignore-submodules=all').strip()==b''
        if startup_admission is not None:_owned_startup_scope(startup_admission,expected)
        return clean

    except (OSError,ValueError,UnicodeError,configparser.Error,subprocess.SubprocessError):
        return False


async def _initialize_owned_module_health():
    global _owned_module_binding,_owned_module_source_admission
    _owned_module_binding=None
    _owned_module_source_admission=None
    if not any(key in os.environ for key in _OWNED_MODULE_ENV):return
    identity=_owned_module_identity()
    if identity is None:raise RuntimeError('Owned module profile unavailable')
    admission=getattr(app.state,'owned_source_admission',None)
    try:
        options={} if admission is None else {'startup_admission':admission}
        clean=await asyncio.wait_for(asyncio.to_thread(_owned_source_is_clean,identity[4],**options),timeout=4)
        if admission is not None:_owned_startup_scope(admission,identity[4])
        if getattr(app.state,'owned_source_admission',None) is not admission:clean=False
        if _owned_module_identity()!=identity:clean=False
    except Exception:
        clean=False
    if clean is not True:raise RuntimeError('Owned module source binding unavailable')
    _owned_module_source_admission=admission
    _owned_module_binding=identity


@app.get('/internal/v2/module/health')
async def owned_module_health(request:Request):
    headers={'Cache-Control':'no-store'}
    if request.scope.get('query_string'):
        return JSONResponse({'error':'MODULE_HEALTH_INVALID_REQUEST'},status_code=400,headers=headers)
    identity=_owned_module_identity()
    if identity is None:
        return JSONResponse({'error':'MODULE_HEALTH_UNAVAILABLE'},status_code=503,headers=headers)
    authorization=request.headers.getlist('authorization')
    if (len(authorization)!=1 or len(authorization[0])>256
            or not secrets.compare_digest(authorization[0].encode('utf-8'),('Bearer '+identity[3]).encode('ascii'))):
        return JSONResponse({'error':'MODULE_HEALTH_FORBIDDEN'},status_code=403,headers=headers)
    if _owned_module_binding!=identity:
        return JSONResponse({'error':'MODULE_HEALTH_UNAVAILABLE'},status_code=503,headers=headers)
    async def probe():
        admission=_owned_module_source_admission
        if getattr(app.state,'owned_source_admission',None) is not admission:return False
        if admission is not None:_owned_startup_scope(admission,identity[4])
        if control_leader is not None and getattr(control_leader,'requires_fencing',True):return False
        if (await control_readiness()).get('ready') is not True:return False
        if admission is not None:_owned_startup_scope(admission,identity[4])
        if getattr(app.state,'owned_source_admission',None) is not admission:return False
        pool=db.pool
        value=await pool.fetchval('SELECT 1')
        if type(value) is not int or value!=1 or db.pool is not pool:return False
        if (await control_readiness()).get('ready') is not True:return False
        if admission is not None:_owned_startup_scope(admission,identity[4])
        if getattr(app.state,'owned_source_admission',None) is not admission:return False
        return (not (control_leader is not None and getattr(control_leader,'requires_fencing',True))
                and _owned_module_identity()==identity and _owned_module_binding==identity)
    try:
        ready=await asyncio.wait_for(probe(),timeout=min(1.0,_MODULE_HEALTH_TIMEOUT)) is True
    except Exception:
        ready=False
    return JSONResponse({'module_id':'grid','version':identity[1],'release_id':identity[2],
                         'instance_token':identity[3],'ready':ready},status_code=200 if ready else 503,headers=headers)


def control_disk_state():
    root=os.path.join(os.environ.get("ProgramData",r"C:\ProgramData"),"BybitClusterGrid")
    return disk_state(root,DiskWatermarks(
        soft_free_gb=float(settings.disk_soft_free_gb),
        hard_free_gb=float(settings.disk_hard_free_gb),
        emergency_free_gb=float(settings.disk_emergency_free_gb)))


async def recovery_profile():
    """Small feedback signal for fleet WAL replay; fail conservatively."""
    state=control_disk_state()["state"]
    cutoff=time.time()-settings.heartbeat_seconds*3
    recovering=sum(1 for v in nodes.values()
        if float(v.get("last_seen",0))>=cutoff and
        (bool(v.get("db_replay_active")) or bool(v.get("micro_replay_active"))))
    share=max(1,recovering)
    if state in ("HARD","EMERGENCY"):
        return {"profile":"PAUSE","minute_per_second":0.0,"micro_per_second":0.0}
    started=time.monotonic()
    try:
        async with db.pool.acquire() as c:
            await c.fetchval("SELECT 1")
            active=int(await c.fetchval("""SELECT count(*) FROM pg_stat_activity
                WHERE datname=current_database() AND state='active'""") or 0)
        latency=(time.monotonic()-started)*1000.0
    except Exception:
        return {"profile":"PAUSE","minute_per_second":0.0,"micro_per_second":0.0}
    if state=="SOFT" or latency>=float(settings.replay_db_latency_pause_ms):
        return {"profile":"PAUSE","minute_per_second":0.0,"micro_per_second":0.0,
                "db_latency_ms":round(latency,1),"db_active":active}
    if latency>=float(settings.replay_db_latency_slow_ms) or active>=settings.strategy_db_active_limit:
        return {"profile":"SLOW",
                "minute_per_second":max(0.1,float(settings.replay_minute_slow_per_second)/share),
                "micro_per_second":max(0.1,float(settings.replay_micro_slow_per_second)/share),
                "db_latency_ms":round(latency,1),"db_active":active}
    return {"profile":"FAST",
            "minute_per_second":max(0.1,float(settings.replay_minute_fast_per_second)/share),
            "micro_per_second":max(0.1,float(settings.replay_micro_fast_per_second)/share),
            "db_latency_ms":round(latency,1),"db_active":active}

def constant_time_equal(left,right):
    """Compare authentication tokens without leaking early string mismatch timing."""
    return secrets.compare_digest(str(left or ""),str(right or ""))


def auth(token):
    configured=str(settings.grid_shared_token or "").strip()
    # Administrative shared-token endpoints must never become public merely
    # because GRID_SHARED_TOKEN was omitted from CONTROL configuration.
    if not configured:
        raise HTTPException(503,"CONTROL administrative authentication is not configured")
    if not constant_time_equal(token,configured):
        raise HTTPException(401,"bad grid token")


@app.get("/health")
async def health():
    """Unauthenticated liveness/readiness probe with no secret data."""
    if db is None or getattr(db,"pool",None) is None:
        raise HTTPException(503,"database not ready")
    try:
        await db.pool.fetchval("SELECT 1")
        fleet_state=await runtime_state(db.pool)
    except Exception:
        log.exception("health probe failed",extra={"event":"health_failed","component":"coordinator"})
        raise HTTPException(503,"database unavailable")
    return {
        "ok": True,
        "pid": __import__("os").getpid(),
        "service": "Bybit Cluster Grid Coordinator",
        "runtime_state": str(fleet_state.get("state","UNKNOWN")),
    }

@app.post("/bootstrap/envelope")
async def create_bootstrap_envelope(payload:dict,x_grid_token:str=Header(default="")):
    """Create short-lived onboarding material without exposing CONTROL OAuth credentials."""
    auth(x_grid_token)
    import datetime
    mode=str(payload.get("install_mode","NORMAL")).upper()
    label=str(payload.get("label") or "grid-node")[:128]
    coordinator_url=str(payload.get("coordinator_url") or "").strip()
    if not coordinator_url or "127.0.0.1" in coordinator_url or "localhost" in coordinator_url.lower():
        raise HTTPException(400,"reachable non-loopback coordinator_url is required")
    ttl_minutes=max(5,min(60,int(payload.get("ttl_minutes",20))))
    expires=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=ttl_minutes)
    try:
        tag=settings.tailscale_node_tags
        tailscale_key=await create_one_time_auth_key(
            settings.tailscale_oauth_client_id,
            settings.tailscale_oauth_client_secret,
            tag,
        )
        enrollment_token=await create_enrollment_token(db.pool,label,expires,mode)
    except (ValueError,TailscaleProvisioningError) as e:
        raise HTTPException(409,str(e))
    return {
        "schema":1,
        "coordinator_url":coordinator_url,
        "install_mode":"AUTO",
        "authorized_mode":mode,
        "enrollment_token":enrollment_token,
        "tailscale_auth_key":tailscale_key,
        "tailscale_tags":tag,
        "expires_at":expires.isoformat(),
    }


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
    # Protect the central database volume, not only each worker's local disk.
    # SOFT pressure keeps minute/live collection but sheds high-rate micro data;
    # HARD/EMERGENCY stops new live assignments until space recovers.
    control_disk=control_disk_state()
    if not live_collection_allowed(control_disk["state"]):
        symbols=[]
    # High-rate microstructure capture remains pilot-only until the volatility
    # selector is implemented; disk SOFT pressure also disables it first.
    micro_symbols=symbols if install_mode=="PILOT" and control_disk["state"]=="NORMAL" else []
    replay=await recovery_profile()
    return {"symbols":symbols,"micro_symbols":micro_symbols,"commands":commands,"control_replica":replica,
            "live_assignments_enabled":bool(symbols),"live_mode":live_mode,
            "install_mode":install_mode,"control_disk_state":control_disk["state"],
            "recovery_profile":replay,
            "runtime_state":fleet_state["state"],"market_work_enabled":market_enabled}

@app.get("/nodes/{node_id}/acceptance")
async def node_acceptance(node_id:str,x_node_credential:str=Header(default="")):
    """Credential-bound cold-install acceptance probe for one worker."""
    if not x_node_credential or not await authenticate_agent(db.pool,node_id,x_node_credential):
        raise HTTPException(403)
    snap=nodes.get(node_id)
    if not snap:
        return {"accepted":False,"reason":"heartbeat_not_seen"}
    age=max(0.0,time.time()-float(snap.get("last_seen",0)))
    return {
        "accepted": age <= settings.heartbeat_seconds*2,
        "last_seen_age_seconds": round(age,2),
        "runtime_state": str(snap.get("runtime_state","UNKNOWN")),
        "pressure_state": str(snap.get("pressure_state","UNKNOWN")),
    }


@app.post("/commands/{command_id}/result")
async def post_command_result(command_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=payload.get("node_id")
    if node_id:
        await node_auth(node_id,x_node_credential,x_grid_token)
    else:
        auth(x_grid_token)
    try:
        updated=await command_result(
            db.pool,
            command_id,
            bool(payload.get("ok")),
            payload.get("result"),
            payload.get("error"),
            node_id=node_id if node_id else None,
        )
    except ValueError:
        raise HTTPException(400,"invalid command ID")
    if not updated:
        raise HTTPException(404,"command not found for authenticated node")
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

@app.post("/control/update")
async def control_update(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    version=str(payload.get("version") or "").strip()
    if not version:
        raise HTTPException(400,"version is required")
    rel=await db.pool.fetchrow("""SELECT r.version,r.package_url,r.sha256,r.enabled,r.channel,s.status AS rollout_status
      FROM agent_releases r LEFT JOIN rollout_state s ON s.version=r.version WHERE r.version=$1""",version)
    if not rel or not rel["enabled"] or rel["channel"]!="stable" or rel["rollout_status"]!="complete":
        raise HTTPException(409,"CONTROL may update only after the promoted stable worker rollout is complete")
    url=str(rel["package_url"]);sha=str(rel["sha256"]).lower()
    if not url.lower().startswith("https://") or len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha):
        raise HTTPException(409,"registered release metadata is invalid")
    data_root=pathlib.Path(os.environ.get("ProgramData",r"C:\\ProgramData"))/"BybitClusterGrid"
    install_root=pathlib.Path(os.environ.get("ProgramFiles",r"C:\\Program Files"))/"BybitClusterGrid"
    pending=install_root/"pending.version"
    if (data_root/"control-update.lock").exists() or (pending.exists() and pending.read_text(encoding="utf-8-sig").strip()):
        raise HTTPException(409,"CONTROL update or release health verification already running")
    python=data_root/"runtime"/"venv"/"Scripts"/"python.exe"
    log_path=data_root/"logs"/"control-self-update.log"
    log_path.parent.mkdir(parents=True,exist_ok=True)
    out=open(log_path,"ab",buffering=0)
    try:
        subprocess.Popen([str(python),"-m","grid.control_self_update",
                          "--version",version,"--url",url,"--sha256",sha],
                         cwd=str(pathlib.Path(__file__).resolve().parents[1]),
                         stdout=out,stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                         close_fds=True)
    finally:
        out.close()
    return {"accepted":True,"version":version,"state":"control_update_started"}

@app.get("/control/update/status")
async def control_update_status(x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    data_root=pathlib.Path(os.environ.get("ProgramData",r"C:\\ProgramData"))/"BybitClusterGrid"
    install_root=pathlib.Path(os.environ.get("ProgramFiles",r"C:\\Program Files"))/"BybitClusterGrid"
    status={}
    try: status=json.loads((data_root/"control-update-status.json").read_text(encoding="utf-8"))
    except (OSError,ValueError): pass
    def marker(name):
        try:return (install_root/name).read_text(encoding="utf-8-sig").strip()
        except OSError:return ""
    current=marker("current.version");previous=marker("previous.version");pending=marker("pending.version")
    journal_version=str(status.get("version") or "")
    if status.get("state")=="staged" and journal_version:
        if current==journal_version and not pending: status["state"]="healthy"
        elif current!=journal_version and not pending: status["state"]="rolled_back"
    status.update({"current":current,"previous":previous,"pending":pending,
                   "running":(data_root/"control-update.lock").exists()})
    return status


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
    # DB-less agents authenticate with their per-node credential.  Do not
    # require the fleet-wide shared CONTROL token on worker machines.
    if not x_node_id or not await authenticate_agent(db.pool,x_node_id,x_node_credential):
        raise HTTPException(403)
    payload=await request.json()
    gate=await runtime_state(db.pool)
    if gate["state"]!="ACTIVE":
        raise HTTPException(423,"market ingestion locked")
    if ingest_storage is None:
        raise HTTPException(503,"ingestion unavailable")
    if not live_collection_allowed(control_disk_state()["state"]):
        raise HTTPException(507,"CONTROL disk pressure")
    await ingest_storage._save_direct(payload, authenticated_identity=x_node_id)
    return {"ok":True}

@app.post("/ingest/event")
async def ingest_event(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default=""),x_node_id:str=Header(default="")):
    # High-rate ingestion uses the same per-node identity as heartbeat.
    # Keeping GRID_SHARED_TOKEN CONTROL-only limits the blast radius of a
    # compromised collector.
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
    # Reject malformed timestamps at the HTTP boundary instead of returning a
    # retryable 500 that can permanently stall the ordered worker WAL.
    if isinstance(event_ts,bool):
        raise HTTPException(400,"invalid micro-event timestamp")
    try:
        event_ts=int(event_ts)
    except (ValueError,TypeError,OverflowError):
        raise HTTPException(400,"invalid micro-event timestamp")
    if event_ts<0 or event_ts>253402300799999:
        raise HTTPException(400,"invalid micro-event timestamp")
    if control_disk_state()["state"]!="NORMAL":
        # Micro events are shed already at SOFT pressure because they are the
        # highest-rate, least essential live stream.
        raise HTTPException(507,"CONTROL disk pressure")
    await db.insert_event(symbol,int(event_ts),event_type,event_payload)
    return {"ok":True}


@app.post("/data-first/requests")
async def submit_data_first(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    try:ident=await enqueue_data_first(db.pool,payload,getattr(app.state,'data_first_policy',None))
    except ValueError:raise HTTPException(409,"DataFirst input/source admission blocked")
    return {'job_id':ident}

@app.post("/data-first/claim")
async def claim_data_first_job(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    if set(payload)!={'node_id'} or type(payload['node_id']) is not str:raise HTTPException(400,"closed node identity required")
    node_id=payload['node_id'];await node_auth(node_id,x_node_credential,x_grid_token)
    runtime=nodes.get(node_id,{})
    if time.time()-float(runtime.get('last_seen',0))>settings.heartbeat_seconds*3:return {'job':None}
    return {'job':await claim_data_first(db.pool,node_id,getattr(app.state,'data_first_policy',None),runtime)}

@app.post("/data-first/jobs/{job_id}/checkpoint")
async def checkpoint_data_first(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    if set(payload)!={'node_id','lease_generation','sequence','state','checkpoint','request_sha256'}:raise HTTPException(400,"closed checkpoint required")
    node_id=payload['node_id'];await node_auth(node_id,x_node_credential,x_grid_token)
    try:result=await publish_data_first(db.pool,job_id,node_id,payload['lease_generation'],payload['sequence'],payload['state'],payload['checkpoint'],getattr(app.state,'data_first_policy',None),request_pin=payload['request_sha256'])
    except (ValueError,TypeError):raise HTTPException(409,"DataFirst checkpoint rejected")
    if result is None:raise HTTPException(409,"DataFirst lease fenced")
    return result

@app.post("/ml/claim")
async def claim_ml_job(payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""))
    if not node_id:raise HTTPException(400,"node_id required")
    await node_auth(node_id,x_node_credential,x_grid_token)
    return {"job":await ml_claim(db.pool,node_id)}

@app.post("/ml/jobs/{job_id}/renew")
async def renew_ml_job(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""));generation=int(payload.get("lease_generation",-1))
    await node_auth(node_id,x_node_credential,x_grid_token)
    if not await ml_renew(db.pool,job_id,node_id,generation):raise HTTPException(409,"stale ML lease")
    return {"ok":True}

@app.get("/ml/jobs/{job_id}/dataset")
async def get_ml_dataset(job_id:str,node_id:str,lease_generation:int,offset:int=0,limit:int=500,
                         x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    await node_auth(node_id,x_node_credential,x_grid_token)
    page=await ml_dataset_page(db.pool,job_id,node_id,lease_generation,offset,limit)
    if page is None:raise HTTPException(409,"stale ML lease")
    return page

@app.post("/ml/jobs/{job_id}/artifact")
async def upload_ml_artifact(job_id:str,request:Request,node_id:str,lease_generation:int,sha256:str,
                             x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    await node_auth(node_id,x_node_credential,x_grid_token)
    if not await ml_train_lease_valid(db.pool,job_id,node_id,lease_generation):
        raise HTTPException(409,"stale or non-training ML lease")
    max_bytes=256*1024*1024
    declared=int(request.headers.get("content-length","0") or 0)
    if declared>max_bytes:raise HTTPException(413,"artifact too large")
    store=LocalArtifactStore(settings.ml_artifact_root)
    fd,tmp=tempfile.mkstemp(prefix="upload-",suffix=".tmp",dir=str(store.root))
    size=0;digest=hashlib.sha256()
    try:
        with os.fdopen(fd,"wb") as f:
            async for chunk in request.stream():
                if not chunk:continue
                size+=len(chunk)
                if size>max_bytes:raise HTTPException(413,"artifact too large")
                digest.update(chunk);f.write(chunk)
            f.flush();os.fsync(f.fileno())
        actual=digest.hexdigest()
        if actual!=sha256:raise HTTPException(400,"artifact sha256 mismatch")
        saved=store.adopt_temp(tmp,size,actual)
        tmp=None
        result=await ml_register_saved_artifact(db.pool,job_id,node_id,lease_generation,saved)
        if result is None:
            store.delete_uri(saved["storage_uri"])
            raise HTTPException(409,"stale ML lease")
        return result
    finally:
        if tmp:
            try:os.unlink(tmp)
            except OSError:pass

@app.post("/ml/jobs/{job_id}/finalize")
async def finalize_ml_job(job_id:str,payload:dict,x_grid_token:str=Header(default=""),x_node_credential:str=Header(default="")):
    node_id=str(payload.get("node_id",""));generation=int(payload.get("lease_generation",-1))
    await node_auth(node_id,x_node_credential,x_grid_token)
    result=await ml_finalize_model(db.pool,job_id,node_id,generation,payload.get("artifact_id"),payload.get("metrics"))
    if not result:raise HTTPException(409,"stale ML lease or artifact")
    return result

@app.get("/status")
async def status(x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    return {"nodes":nodes,"assignments":assignments,"instrument_count":len(instruments)}

@app.get("/scientific/status")
async def scientific_status(x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    if scientific_service is None:
        raise HTTPException(503,"scientific research service unavailable")
    pending=await db.pool.fetchval("SELECT count(*) FROM scientific_outcome_requests WHERE status='PENDING'")
    counts=await db.pool.fetch("""SELECT status,count(*) n FROM scientific_hypotheses GROUP BY status""")
    out=scientific_service.status()
    out["pending_outcomes"]=int(pending or 0)
    out["hypotheses"]={str(r["status"]):int(r["n"]) for r in counts}
    mining=await db.pool.fetchrow("""SELECT COALESCE(sum(hypotheses_tested),0) tested,
      max(last_run_at) last_run_at FROM scientific_mining_families""")
    last=await db.pool.fetchrow("""SELECT split_key,candidate_count,accepted_count,status,completed_at
      FROM scientific_mining_runs ORDER BY started_at DESC LIMIT 1""")
    out["pattern_mining"]={"hypotheses_tested":int(mining["tested"] or 0),
                           "last_run_at":mining["last_run_at"],
                           "last":dict(last) if last else None}
    sim=await db.pool.fetch("""SELECT status,count(*) n FROM scientific_simulation_runs GROUP BY status""")
    out["simulation_gate"]={str(r["status"]):int(r["n"]) for r in sim}
    return out

@app.get("/scientific/hypotheses")
async def scientific_hypotheses(status_filter:str="",limit:int=100,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    limit=max(1,min(500,int(limit)))
    rows=await db.pool.fetch("""SELECT id,fingerprint,method,pattern,horizon_ms,direction,
      feature_version,status,research_only,first_seen_at,updated_at,validated_at,rejected_at
      FROM scientific_hypotheses WHERE ($1='' OR status=$1)
      ORDER BY updated_at DESC LIMIT $2""",str(status_filter).upper(),limit)
    return {"hypotheses":[dict(r) for r in rows]}

@app.get("/scientific/hypotheses/{hypothesis_id}/evidence")
async def scientific_hypothesis_evidence(hypothesis_id:str,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    rows=await db.pool.fetch("""SELECT experiment_key,symbol,regime,split_key,sample_count,
      mean_return_bps,hit_rate,cost_bps,dataset_cutoff,passed,metrics,created_at
      FROM scientific_hypothesis_evidence WHERE hypothesis_id=$1::uuid
      ORDER BY created_at""",hypothesis_id)
    return {"hypothesis_id":hypothesis_id,"evidence":[dict(r) for r in rows]}

@app.get("/lifecycle")
async def lifecycle_status(x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    p=await get_phase(db.pool)
    p["capabilities"]=phase_capabilities(p["phase"])
    return p

@app.post("/lifecycle/phase/{target}")
async def lifecycle_advance(target:str,payload:dict|None=None,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    try:return await advance_phase(db.pool,target,(payload or {}).get("details"))
    except ValueError as e:raise HTTPException(409,str(e))

@app.post("/scientific/history/import")
async def scientific_history_import(payload:dict,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    phase=await get_phase(db.pool)
    if phase["phase"] in ("LIVE_LEARNING","PAPER_TRADING"):
        # Later phases may import additional historical bundles as priors, but
        # the lifecycle itself must never regress.
        try:return await import_historical_science(db.pool,payload)
        except ValueError as e:raise HTTPException(400,str(e))
    try:result=await import_historical_science(db.pool,payload)
    except ValueError as e:raise HTTPException(400,str(e))
    # Verified Strattester handoff is proof that the historical prerequisites
    # were completed outside Grid. Advance the local lifecycle monotonically.
    current=(await get_phase(db.pool))["phase"]
    for target in ("MARKET_HISTORY_SYNC","HISTORICAL_STRATEGY_RESEARCH",
                   "HISTORICAL_SCIENCE_BOOTSTRAP","GRID_IMPORT"):
        if current==target:continue
        if PHASES.index(current)<PHASES.index(target):
            await advance_phase(db.pool,target,{"historical_science_bundle":result["bundle_id"],
                                                "handoff_source":"strattester"})
            current=target
    return result

@app.get("/scientific/simulations")
async def scientific_simulations(status_filter:str="",limit:int=100,x_grid_token:str=Header(default="")):
    auth(x_grid_token)
    limit=max(1,min(500,int(limit)))
    rows=await db.pool.fetch("""SELECT r.id,r.hypothesis_id,h.fingerprint,h.pattern,h.horizon_ms,
      r.simulation_version,r.dataset_cutoff,r.status,r.metrics,r.stress_metrics,r.reason,
      r.created_at,r.completed_at FROM scientific_simulation_runs r
      JOIN scientific_hypotheses h ON h.id=r.hypothesis_id
      WHERE ($1='' OR r.status=$1) ORDER BY r.created_at DESC LIMIT $2""",
      str(status_filter).upper(),limit)
    return {"simulations":[dict(r) for r in rows]}

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

async def rebalance():
    """Assign each live symbol to one eligible healthy collector.

    NORMAL nodes share the full universe. During pilot validation, PILOT nodes
    share only the bounded pilot universe. A symbol has one owner; no implicit
    replication to every worker is allowed.
    """
    global assignments
    alive={k:v for k,v in nodes.items() if time.time()-v["last_seen"] < settings.heartbeat_seconds*3}
    work_alive={k:v for k,v in alive.items() if node_accepts_work(v)}
    scores={k:capacity_score(v,settings.resource_cpu_limit,settings.resource_ram_limit,
                             settings.resource_disk_free_gb,settings.resource_reserve_cores) for k,v in work_alive.items()}
    scores={k:v for k,v in scores.items() if v>0}
    if not scores:
        assignments={}
        return

    eligible={}
    pilot_nodes={}
    normal_nodes={}
    for nid,score in scores.items():
        install_mode=await registered_install_mode(db.pool,nid)
        live_mode=await node_live_mode(db.pool,nid)
        if install_mode=="NORMAL" and live_mode=="NORMAL":
            normal_nodes[nid]=score
        elif install_mode=="PILOT" and live_mode=="PILOT_VALIDATING":
            pilot_nodes[nid]=score

    # Prefer production-normal collectors for the full universe. Before fleet
    # expansion, pilot collectors divide the canary universe between themselves.
    if normal_nodes:
        eligible=normal_nodes
        universe=list(instruments.keys())
    elif pilot_nodes:
        eligible=pilot_nodes
        universe=pilot_universe(instruments)
    else:
        assignments={}
        return

    eligible_heartbeats={nid:alive[nid] for nid in eligible}
    proposed=weighted_assign(universe,eligible,eligible_heartbeats)
    assignments=stabilize_assignments(proposed,assignments,eligible_heartbeats,
                                      getattr(settings,"assignment_max_churn_fraction",.10))

@app.on_event("startup")
async def startup():
    global db, ingest_storage, background_tasks, coordination_authority, control_leader, control_task
    await _initialize_owned_module_health()
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
                instruments={x["symbol"]:x for x in xs}; await rebalance()
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

    async def start_services(epoch=None):
        global background_tasks
        await _prepare_control_services(epoch)
        background_tasks = [
            asyncio.create_task(loop()),
            asyncio.create_task(telegram_loop(db,nodes)),
            asyncio.create_task(retention_scheduler(db.pool,settings)),
            asyncio.create_task(maintenance_scheduler(db.pool,settings)),
            asyncio.create_task(ml_orchestrator.run()),
            asyncio.create_task(scientific_service.run()),
        ]

    # Configuration and independent-fence readiness precede all DB/writer startup.
    coordination_authority = await coordinator_authority(settings,
        external_fence_verifier=getattr(app.state, 'external_fence_verifier', None))
    bootstrap_logging()
    install_asyncio_exception_filter(asyncio.get_running_loop())
    try:
        db=await prepare_database()
    except BaseException:
        if coordination_authority is not None:
            await coordination_authority.close()
            coordination_authority=None
        raise
    if coordination_authority is None:
        await start_services()
        return
    control_leader=FloatingLeader(db.pool, settings.grid_control_node_id,
        settings.grid_leader_lease_seconds, settings.grid_leader_renew_seconds,
        coordination=coordination_authority,
        cleanup_timeout_seconds=settings.grid_leader_cleanup_timeout_seconds)
    app.state.grid_lease_guard=floating_leader_guard(control_leader)
    control_task=asyncio.create_task(control_leader.run(start_services, _stop_control_services))


async def _prepare_control_services(epoch=None):
    global ingest_storage, background_tasks, ml_orchestrator, scientific_service
    await ensure_instrument_schema(db.pool)
    await ensure_strategy_schema(db.pool)
    await ensure_plugin_schema(db.pool)
    await ensure_control_schema(db.pool)
    await ensure_update_schema(db.pool)
    await ensure_enrollment_schema(db.pool)
    await ensure_runtime_gate(db.pool)
    await ensure_retention_schema(db.pool)
    ingest_storage=Storage()
    ingest_storage.pool=db.pool
    await ingest_storage.feature_builder.start(db.pool)
    scientific_service=ScientificResearchService(db.pool)
    await scientific_service.start()
    ingest_storage.scientific=scientific_service
    ingest_storage.derived=__import__('grid.derived_pipeline',fromlist=['DerivedPipeline']).DerivedPipeline(db.pool)
    await ingest_storage.derived.start()
    async def ml_nodes():
        cutoff=time.time()-settings.heartbeat_seconds*3
        return {nid:dict(v) for nid,v in nodes.items() if float(v.get("last_seen",0))>=cutoff}
    async def ml_health():
        snap=resource_snapshot()
        try:
            active=await db.pool.fetchval("""SELECT count(*) FROM pg_stat_activity
              WHERE datname=current_database() AND state='active'""")
        except Exception:
            active=settings.strategy_db_active_limit
        return {"cpu_pct":snap["cpu_pct"],"ram_pct":snap["ram_pct"],
                "disk_free_gb":snap["disk_free"]/(1024**3),
                "db_latency_ms":0 if int(active or 0)<settings.strategy_db_active_limit else 9999,
                "db_queue_ratio":min(1.0,int(active or 0)/max(1,settings.strategy_db_active_limit))}
    ml_orchestrator=MLOrchestratorService(db.pool,MLDispatcher(db.pool,ml_nodes,data_first_policy=getattr(app.state,"data_first_policy",None)),ml_health)


async def _stop_control_services():
    await shutdown(close_database=False)


@app.on_event("shutdown")
async def shutdown(close_database=True):
    global ingest_storage, background_tasks, ml_orchestrator, scientific_service
    global control_leader, control_task, coordination_authority
    if close_database and control_leader is not None:
        control_leader.stop()
        if control_task is not None:
            await control_task
        control_task=None
        control_leader=None
    if ml_orchestrator is not None:
        ml_orchestrator.stop()
    if scientific_service is not None:
        scientific_service.stop()
    tasks = list(background_tasks)
    background_tasks = []

    for task in tasks:
        task.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    if ingest_storage is not None:
        # CONTROL borrows the Database pool for direct ingest. Stop the derived
        # pipeline before closing the shared pool so no background writer can race
        # shutdown/reboot.
        derived=getattr(ingest_storage,"derived",None)
        if derived is not None:
            close=getattr(derived,"close",None)
            if close is not None:
                await close()
        ingest_storage = None

    ml_orchestrator=None
    scientific_service=None

    if close_database:
        if coordination_authority is not None:
            await coordination_authority.close()
            coordination_authority=None
        if db is not None and db.pool is not None:
            await db.pool.close()
            db.pool=None
