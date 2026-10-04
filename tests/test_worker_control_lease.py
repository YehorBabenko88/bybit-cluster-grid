import asyncio,time
from grid.worker import Worker
from grid.config import settings


def test_worker_drains_live_assignment_after_control_heartbeat_lease(monkeypatch):
    async def run():
        w=Worker()
        w.wanted={"BTCUSDT"};w.micro_wanted={"BTCUSDT"}
        w.last_control_ok=time.monotonic()-max(20,settings.heartbeat_seconds*4)
        called=[]
        async def reconcile():called.append(True)
        monkeypatch.setattr(w,"reconcile",reconcile)
        assert await w.fail_closed_if_control_stale() is True
        assert w.wanted==set() and w.micro_wanted==set()
        assert w.runtime_state=="CONTROL_UNREACHABLE"
        assert called==[True]
    asyncio.run(run())
