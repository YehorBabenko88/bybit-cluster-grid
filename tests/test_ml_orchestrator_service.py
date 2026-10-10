import asyncio
from grid.ml_adaptive_load import AdaptiveConcurrency
from grid.ml_orchestrator_service import MLOrchestratorService,OBSERVING,DEGRADED

class Pool:
    def __init__(self):self.sql=[]
    def acquire(self):return self
    def transaction(self):return self
    async def __aenter__(self):return self
    async def __aexit__(self,*a):pass
    async def execute(self,sql,*a):self.sql.append(sql);return "UPDATE 1"
    async def fetchrow(self,*a):return {"owner":a[1] if len(a)>1 else "x","lease_until":None}
    async def fetchval(self,sql,*a):return 1 if "FOR UPDATE" in sql else True

def test_recovery_requeues_expired_assignments_and_runs():
    async def run():
        p=Pool()
        async def dispatch(*a):return []
        async def health():return {}
        s=MLOrchestratorService(p,dispatch,health)
        await s.recover()
        assert s.state==OBSERVING
        assert "('running','assigned')" in p.sql[1]
    asyncio.run(run())

def test_pressure_can_pause_all_ml_work():
    c=AdaptiveConcurrency(min_workers=0,max_workers=4);c.current=1
    assert c.update(95,95,500,.95,5)==0

def test_recovery_only_runs_for_leader_and_repeats_after_restart(monkeypatch):
    async def run():
        p=Pool()
        calls=[]
        async def dispatch(*a,**kw):
            calls.append("dispatch")
            return []
        async def health():
            return {"cpu_pct":0,"ram_pct":0,"db_latency_ms":0,
                    "db_queue_ratio":0,"disk_free_gb":1000}
        async def leader(*a):
            return True
        async def follower(*a):
            return False
        import grid.ml_orchestrator_service as module
        s=MLOrchestratorService(p,dispatch,health)
        monkeypatch.setattr(module,"acquire_service_lease",follower)
        assert (await s.tick())["leader"] is False
        assert p.sql==[]
        monkeypatch.setattr(module,"acquire_service_lease",leader)
        await s.tick()
        first=len(p.sql)
        assert first==4
        await s.tick()
        assert len(p.sql)==2*first
        restarted=MLOrchestratorService(p,dispatch,health)
        await restarted.tick()
        assert len(p.sql)==4*first
    asyncio.run(run())

def test_leadership_loss_during_recovery_prevents_dispatch(monkeypatch):
    async def run():
        p=Pool()
        attempts=[]
        dispatches=[]
        async def leadership(*args):
            attempts.append(True)
            return len(attempts)==1
        async def dispatch(*args,**kw):
            dispatches.append(args)
            return []
        async def health():
            return {"cpu_pct":0,"ram_pct":0,"db_latency_ms":0,
                    "db_queue_ratio":0,"disk_free_gb":1000}
        import grid.ml_orchestrator_service as module
        monkeypatch.setattr(module,"acquire_service_lease",leadership)
        s=MLOrchestratorService(p,dispatch,health)
        result=await s.tick()
        assert result["leader"] is False
        assert len(attempts)==2
        assert len(p.sql)==3
        assert dispatches==[]
        assert s.state==OBSERVING
    asyncio.run(run())
