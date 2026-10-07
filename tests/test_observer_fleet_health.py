import asyncio,time
from grid.fleet_health import fleet_health

class Pool:
    async def fetchrow(self,*a): return None
    async def fetch(self,*a): return []

def test_offline_observer_does_not_degrade_production():
    now=time.time()
    nodes={
      "WORK":{"node_role":"WORKER","last_seen":now,"integrity_ok":True},
      "HOME":{"node_role":"DEV_OBSERVER","last_seen":now-1000,"integrity_ok":True},
    }
    r=asyncio.run(fleet_health(Pool(),nodes,10))
    assert r["offline_observers"]==["HOME"]
    assert r["offline_workers"]==[]
    assert r["production_degraded"] is False

def test_offline_worker_degrades_production():
    now=time.time()
    nodes={
      "WORK":{"node_role":"WORKER","last_seen":now-1000,"integrity_ok":True},
      "HOME":{"node_role":"DEV_OBSERVER","last_seen":now,"integrity_ok":True},
    }
    r=asyncio.run(fleet_health(Pool(),nodes,10))
    assert r["offline_workers"]==["WORK"]
    assert r["production_degraded"] is True
