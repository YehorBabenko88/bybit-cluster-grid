import os, platform, socket, uuid, time
import psutil

NODE_ID = os.getenv("NODE_ID") or f"{socket.gethostname()}-{uuid.getnode():x}"
STARTED_AT=time.time()\n\ndef agent_version():\n    root=os.getenv("ProgramFiles")\n    if not root: return os.getenv("GRID_VERSION","bootstrap")\n    p=os.path.join(root,"BybitClusterGrid","current.version")\n    try:\n        with open(p,"r",encoding="utf-8") as f: return f.read().strip() or "bootstrap"\n    except OSError:\n        return os.getenv("GRID_VERSION","bootstrap")

def snapshot():
    vm=psutil.virtual_memory()
    disk=psutil.disk_usage(os.getenv("GRID_DATA_PATH","."))
    proc=psutil.Process()
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
        "process_rss":proc.memory_info().rss,
        "process_cpu_pct":proc.cpu_percent(interval=None),
        "uptime_s":int(time.time()-STARTED_AT),\n        "agent_version":agent_version(),
    }

def capacity_score(s,cpu_limit=75,ram_limit=78,min_disk_gb=25,reserve_cores=2):
    if s["disk_free"] < min_disk_gb*1024**3 or s["cpu_pct"] >= cpu_limit or s["ram_pct"] >= ram_limit:
        return 0.0
    cores=max(1,s["cpu_count"]-reserve_cores)
    cpu_headroom=max(0.05,1-s["cpu_pct"]/100)
    ram_headroom=max(0.05,s["ram_available"]/s["ram_total"])
    disk_headroom=min(1.0,s["disk_free"]/max(s["disk_total"],1))
    return cores*cpu_headroom*ram_headroom*max(0.25,disk_headroom)
