import os,psutil
from .config import settings
from .runtime_gate import market_work_allowed

def pause_flag():
    return os.path.join(os.environ.get("ProgramData",r"C:\\ProgramData"),"BybitClusterGrid","bootstrap.pause")
def stop_flag():
    return os.path.join(os.environ.get("ProgramData",r"C:\\ProgramData"),"BybitClusterGrid","operator.stop")

async def background_work_allowed(pool):
    if os.path.exists(stop_flag()):
        return False,["operator_stopped"]
    if os.path.exists(pause_flag()):
        return False,["paused"]
    # Fail closed: background/archive/strategy/learning work is forbidden until
    # the persistent fleet gate has explicitly entered ACTIVE.
    if not await market_work_allowed(pool):
        return False,["runtime_gate"]
    cpu=psutil.cpu_percent(interval=None)
    ram=psutil.virtual_memory().percent
    disk=psutil.disk_usage(os.environ.get("GRID_DATA_PATH",os.environ.get("ProgramData",os.getcwd()))).free/(1024**3)
    reasons=[]
    if cpu>=settings.resource_cpu_limit:reasons.append("cpu")
    if ram>=settings.resource_ram_limit:reasons.append("ram")
    if disk<settings.resource_disk_free_gb:reasons.append("disk")
    try:
        active=await pool.fetchval("""SELECT count(*) FROM pg_stat_activity
          WHERE datname=current_database() AND state='active'""")
        if int(active or 0)>=settings.strategy_db_active_limit:reasons.append("db")
    except Exception:
        reasons.append("db_unavailable")
    return not reasons,reasons
