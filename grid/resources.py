import os, platform, socket, uuid
import psutil

NODE_ID = os.getenv("NODE_ID") or f"{socket.gethostname()}-{uuid.getnode():x}"

def snapshot():
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(os.getenv("GRID_DATA_PATH", "."))
    return {
        "node_id": NODE_ID,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu_count": psutil.cpu_count(logical=True) or 1,
        "cpu_pct": psutil.cpu_percent(interval=0.25),
        "ram_total": vm.total,
        "ram_available": vm.available,
        "ram_pct": vm.percent,
        "disk_free": disk.free,
    }

def capacity_score(s, cpu_limit=75, ram_limit=78, min_disk_gb=25, reserve_cores=2):
    if s["disk_free"] < min_disk_gb * 1024**3 or s["cpu_pct"] >= cpu_limit or s["ram_pct"] >= ram_limit:
        return 0.0
    cores = max(1, s["cpu_count"] - reserve_cores)
    cpu_headroom = max(0.05, 1 - s["cpu_pct"]/100)
    ram_headroom = max(0.05, s["ram_available"]/s["ram_total"])
    return cores * cpu_headroom * ram_headroom
