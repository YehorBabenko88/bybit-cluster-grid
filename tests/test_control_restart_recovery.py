import asyncio
from grid import ml_orchestrator_service as svc


class Pool:
    def __init__(self):self.execs=[]
    async def execute(self,sql,*args):self.execs.append(sql);return "DELETE 0"


def test_control_restart_uses_fenced_recovery_path(monkeypatch):
    called=[]
    async def recover(pool):
        called.append(pool)
        return {"recovered":1,"failed":0}
    monkeypatch.setattr(svc,"recover_expired_ml_jobs",recover)
    async def health():return {}
    async def dispatch(*args):return []
    async def run():
        p=Pool();o=svc.MLOrchestratorService(p,dispatch,health)
        await o.recover()
        assert called==[p]
        assert o.state==svc.OBSERVING
        assert any("ml_resource_reservations" in q for q in p.execs)
    asyncio.run(run())
