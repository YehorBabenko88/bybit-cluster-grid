import asyncio
from grid.ml_adaptive_load import AdaptiveConcurrency
from grid.ml_orchestrator_service import MLOrchestratorService,OBSERVING,DEGRADED

class Pool:
    def __init__(self):self.sql=[]
    async def execute(self,sql,*a):self.sql.append(sql);return "UPDATE 1"
    async def fetch(self,sql,*a):self.sql.append(sql);return []
    async def fetchrow(self,*a):return {"owner":a[1] if len(a)>1 else "x","lease_until":None}

def test_recovery_requeues_expired_assignments_and_runs():
    async def run():
        p=Pool()
        async def dispatch(*a):return []
        async def health():return {}
        s=MLOrchestratorService(p,dispatch,health)
        await s.recover()
        assert s.state==OBSERVING
        assert any("('assigned','running')" in sql for sql in p.sql)
    asyncio.run(run())

def test_pressure_can_pause_all_ml_work():
    c=AdaptiveConcurrency(min_workers=0,max_workers=4);c.current=1
    assert c.update(95,95,500,.95,5)==0
