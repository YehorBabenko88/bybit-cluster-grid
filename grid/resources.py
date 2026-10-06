import os, platform, socket, uuid, time
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

def ml_runtime_ready():
    try:
        import xgboost, lightgbm, sklearn  # noqa: F401
        return True
    except (ImportError,OSError):
        return False

def agent_version():
    root=os.getenv("ProgramFiles")
    if not root: return os.getenv("GRID_VERSION","bootstrap")
    p=os.path.join(root,"BybitClusterGrid","current.version")
    try:
        with open(p,"r",encoding="utf-8") as f: return f.read().strip() or "bootstrap"
    except OSError:
        return os.getenv("GRID_VERSION","bootstrap")

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
    }

def capacity_score(s,cpu_limit=75,ram_limit=78,min_disk_gb=25,reserve_cores=2):
    if s["disk_free"] < min_disk_gb*1024**3 or s["cpu_pct"] >= cpu_limit or s["ram_pct"] >= ram_limit:
        return 0.0
    cores=max(1,s["cpu_count"]-reserve_cores)
    cpu_headroom=max(0.05,1-s["cpu_pct"]/100)
    ram_headroom=max(0.05,s["ram_available"]/s["ram_total"])
    disk_headroom=min(1.0,s["disk_free"]/max(s["disk_total"],1))
    return cores*cpu_headroom*ram_headroom*max(0.25,disk_headroom)
