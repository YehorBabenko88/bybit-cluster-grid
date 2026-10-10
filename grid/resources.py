import os, platform, socket, uuid, time, subprocess, json, threading
import psutil
from .config import settings
from .disk_guard import DiskWatermarks,disk_state
from .resource_trend import ResourceTrend

def _node_id():
    explicit=os.getenv("NODE_ID","").strip()
    if explicit:
        return explicit
    programdata=os.getenv("PROGRAMDATA")
    if programdata:
        path=os.path.join(programdata,"BybitClusterGrid","secrets","node.id")
        try:
            with open(path,"r",encoding="ascii") as f:
                persisted=f.read().strip()
            if persisted:
                return persisted
        except OSError:
            pass
    # Bootstrap-only fallback. Enrollment persists this value in node.id so
    # later NIC/Tailscale changes cannot silently create a new agent identity.
    return f"{socket.gethostname()}-{uuid.getnode():x}"

NODE_ID = _node_id()
STARTED_AT=time.time()
_RESOURCE_TREND=ResourceTrend()
_STORAGE_CACHE={"at":0.0,"value":{}}
_ML_READY_CACHE={"at":0.0,"value":False,"running":False,"journal_signature":None}
_ML_READY_LOCK=threading.Lock()

def _tree_bytes(root):
    total=0
    try:
        for base,dirs,files in os.walk(root):
            for name in files:
                try: total+=os.path.getsize(os.path.join(base,name))
                except OSError: pass
    except OSError:
        pass
    return total

def local_storage_usage(cache_seconds=300):
    """Bounded-frequency local Grid footprint telemetry for DB-less agents."""
    now=time.time()
    if now-_STORAGE_CACHE["at"] < cache_seconds and _STORAGE_CACHE["value"]:
        return dict(_STORAGE_CACHE["value"])
    root=os.path.join(os.getenv("ProgramData",os.getcwd()),"BybitClusterGrid")
    parts={}
    for key,name in (("spool","spool"),("micro_spool","micro-spool"),("logs","logs"),
                     ("ml_artifacts","ml-artifacts"),("strategy_cache","runtime_strategies")):
        parts[key+"_bytes"]=_tree_bytes(os.path.join(root,name))
    parts["grid_local_data_bytes"]=_tree_bytes(root)
    _STORAGE_CACHE.update(at=now,value=parts)
    return dict(parts)

def _probe_ml_runtime(python,journal):
    """Run heavy imports off the worker heartbeat thread; fail closed."""
    ready=False
    try:
        if os.path.isfile(python) and os.path.isfile(journal):
            with open(journal,encoding="utf-8-sig") as f:
                state=json.load(f)
            if state.get("status")=="ready":
                result=subprocess.run(
                    [python,"-c","import aiohttp,asyncpg,psutil,pydantic,httpx,websockets,numpy,scipy,sklearn,joblib,xgboost,lightgbm"],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    timeout=20,check=False,
                )
                ready=result.returncode==0
    except (OSError,ValueError,subprocess.TimeoutExpired):
        ready=False
    finally:
        try:
            stat=os.stat(journal)
            signature=(stat.st_mtime_ns,stat.st_size)
        except OSError:
            signature=None
        with _ML_READY_LOCK:
            if signature!=_ML_READY_CACHE["journal_signature"]:
                ready=False
            _ML_READY_CACHE.update(at=time.monotonic(),value=ready,running=False)


def ml_runtime_ready():
    """Nonblocking probe with immediate journal-change invalidation."""
    now=time.monotonic()
    root=os.path.join(os.getenv("ProgramData",r"C:\ProgramData"),"BybitClusterGrid","runtime")
    python=os.path.join(root,"ml-venv","Scripts","python.exe")
    journal=os.path.join(root,"ml-bootstrap.json")
    try:
        stat=os.stat(journal)
        signature=(stat.st_mtime_ns,stat.st_size)
    except OSError:
        signature=None
    with _ML_READY_LOCK:
        if signature!=_ML_READY_CACHE["journal_signature"]:
            _ML_READY_CACHE.update(at=0.0,value=False,journal_signature=signature)
        if signature is None:
            return False
        if _ML_READY_CACHE["running"]:
            return False
        if _ML_READY_CACHE["at"] and now-_ML_READY_CACHE["at"]<60:
            return _ML_READY_CACHE["value"]
        _ML_READY_CACHE.update(value=False,running=True)
        try:
            threading.Thread(target=_probe_ml_runtime,args=(python,journal),
                             name="grid-ml-readiness",daemon=True).start()
        except RuntimeError:
            _ML_READY_CACHE.update(at=now,value=False,running=False)
    return False

def agent_version():
    root=os.getenv("ProgramFiles")
    if not root: return os.getenv("GRID_VERSION","bootstrap")
    p=os.path.join(root,"BybitClusterGrid","current.version")
    try:
        with open(p,"r",encoding="utf-8") as f: return f.read().strip() or "bootstrap"
    except OSError:
        return os.getenv("GRID_VERSION","bootstrap")

def normalized_node_role(value=None):
    role=str(value if value is not None else settings.node_role or "WORKER").strip().upper()
    return role if role in {"WORKER","CONTROL","DEV_OBSERVER"} else "WORKER"

def node_accepts_work(snapshot):
    return normalized_node_role(snapshot.get("node_role")) in {"WORKER","CONTROL"}

def node_accepts_control(snapshot):
    return normalized_node_role(snapshot.get("node_role")) == "CONTROL"

def snapshot():
    vm=psutil.virtual_memory()
    disk=psutil.disk_usage(os.getenv("GRID_DATA_PATH","."))
    proc=psutil.Process()
    disk_pressure=disk_state(os.getenv("GRID_DATA_PATH","."),DiskWatermarks(
        soft_free_gb=settings.disk_soft_free_gb,
        hard_free_gb=settings.disk_hard_free_gb,
        emergency_free_gb=settings.disk_emergency_free_gb))["state"]
    trend=_RESOURCE_TREND.add(proc.memory_info().rss)
    return {
        "node_id":NODE_ID,
        "node_role":normalized_node_role(),
        "accepts_work":normalized_node_role() in {"WORKER","CONTROL"},
        "accepts_control":normalized_node_role()=="CONTROL",
        "hostname":socket.gethostname(),
        "platform":platform.platform(),
        "cpu_count":psutil.cpu_count(logical=True) or 1,
        "cpu_pct":psutil.cpu_percent(interval=0.25),
        "load_1m":(psutil.getloadavg()[0] if hasattr(psutil,"getloadavg") else None),
        "ram_total":vm.total,
        "ram_available":vm.available,
        "ram_pct":vm.percent,
        "disk_total":disk.total,
        "disk_free":disk.free,
        "disk_pressure_state":disk_pressure,
        "process_rss":proc.memory_info().rss,
        "process_rss_peak":trend["rss_peak"],
        "process_rss_growth":trend["rss_growth_bytes"],
        "process_rss_sustained_growth":trend["sustained_growth"],
        "process_cpu_pct":proc.cpu_percent(interval=None),
        "uptime_s":int(time.time()-STARTED_AT),
        "agent_version":agent_version(),
        "ml_runtime_ready":ml_runtime_ready(),
        **local_storage_usage(),
    }

def capacity_score(s,cpu_limit=75,ram_limit=78,min_disk_gb=25,reserve_cores=2):
    if s["disk_free"] < min_disk_gb*1024**3 or s["cpu_pct"] >= cpu_limit or s["ram_pct"] >= ram_limit:
        return 0.0
    cores=max(1,s["cpu_count"]-reserve_cores)
    cpu_headroom=max(0.05,1-s["cpu_pct"]/100)
    ram_headroom=max(0.05,s["ram_available"]/s["ram_total"])
    disk_headroom=min(1.0,s["disk_free"]/max(s["disk_total"],1))
    return cores*cpu_headroom*ram_headroom*max(0.25,disk_headroom)
