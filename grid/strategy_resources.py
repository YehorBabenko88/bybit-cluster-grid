import time
from .resources import snapshot

def strategy_allowed(settings):
    s=snapshot()
    reasons=[]
    cpu_soft=getattr(settings,"strategy_cpu_soft_limit",60)
    ram_soft=getattr(settings,"strategy_ram_soft_limit",72)
    disk_min=getattr(settings,"strategy_disk_free_gb",max(settings.resource_disk_free_gb,30))
    if s["cpu_pct"] >= cpu_soft: reasons.append("cpu")
    if s["ram_pct"] >= ram_soft: reasons.append("ram")
    if s["disk_free"] < disk_min*1024**3: reasons.append("disk")
    return (not reasons),s,reasons

async def database_pressure(pool,settings):
    async with pool.acquire() as c:
        active=await c.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='active'")
        size=await c.fetchval("SELECT pg_database_size(current_database())")
    max_active=getattr(settings,"strategy_db_active_limit",20)
    return {
        "ok":active < max_active,
        "active_connections":active,
        "database_bytes":size,
        "reason":None if active < max_active else "db_active_connections",
    }
