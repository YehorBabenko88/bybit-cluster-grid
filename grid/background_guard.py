import os,psutil
from .config import settings
from .runtime_gate import market_work_allowed
from .disk_guard import DiskWatermarks,disk_state,heavy_work_allowed

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
    data_path=os.environ.get("GRID_DATA_PATH",os.environ.get("ProgramData",os.getcwd()))
    disk=disk_state(data_path,DiskWatermarks(
        soft_free_gb=settings.disk_soft_free_gb,
        hard_free_gb=settings.disk_hard_free_gb,
        emergency_free_gb=settings.disk_emergency_free_gb))
    reasons=[]
    if cpu>=settings.resource_cpu_limit:reasons.append("cpu")
    if ram>=settings.resource_ram_limit:reasons.append("ram")
    if not heavy_work_allowed(disk["state"]):reasons.append("disk_"+disk["state"].lower())
    try:
        active=await pool.fetchval("""SELECT count(*) FROM pg_stat_activity
          WHERE datname=current_database() AND state='active'""")
        if int(active or 0)>=settings.strategy_db_active_limit:reasons.append("db")
    except Exception:
        reasons.append("db_unavailable")
    return not reasons,reasons
