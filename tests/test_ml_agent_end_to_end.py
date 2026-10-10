from pathlib import Path
import os,time
from grid.ml_agent_worker import cleanup_stale_workspaces


def test_worker_starts_db_less_ml_agent_loop():
    s=Path("grid/worker.py").read_text(encoding="utf-8")
    assert "MLTransportClient(NODE_ID)" in s
    assert "ml_agent_loop" in s
    assert 'self.runtime_state=="ACTIVE"' in s
    assert 'disk_pressure_state")=="NORMAL"' in s


def test_control_starts_ml_orchestrator():
    s=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert "MLOrchestratorService" in s
    assert "MLDispatcher" in s
    assert "asyncio.create_task(ml_orchestrator.run())" in s
    assert "ml_orchestrator.stop()" in s


def test_bundle_mode_never_needs_postgres_on_agent():
    s=Path("grid/ml_compute_entry.py").read_text(encoding="utf-8")
    block=s.split("async def train_bundle",1)[1].split("async def main_async",1)[0]
    assert "Database" not in block
    assert "TrainingWorker" not in block
    assert "TabularBoostBackend" in block


def test_stale_workspace_cleanup(tmp_path,monkeypatch):
    monkeypatch.setenv("ProgramData",str(tmp_path))
    root=tmp_path/"BybitClusterGrid"/"ml-work"
    old=root/"job-old";old.mkdir(parents=True)
    fresh=root/"job-fresh";fresh.mkdir()
    past=time.time()-90000
    os.utime(old,(past,past))
    removed=cleanup_stale_workspaces(86400)
    assert removed==1
    assert not old.exists() and fresh.exists()


def test_ml_agent_recovers_after_transient_claim_error(monkeypatch):
    import asyncio
    import grid.ml_agent_worker as agent

    class Client:
        def __init__(self):
            self.calls = 0
        async def claim(self):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("temporary coordinator outage")
            return None

    async def run():
        stop = asyncio.Event()
        client = Client()
        async def stop_after_recovery():
            while client.calls < 2:
                await asyncio.sleep(.01)
            stop.set()
        watcher = asyncio.create_task(stop_after_recovery())
        try:
            await asyncio.wait_for(agent.ml_agent_loop(client, stop, poll_seconds=.02), timeout=2)
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        assert client.calls >= 2

    monkeypatch.setattr(agent, "cleanup_stale_workspaces", lambda: 0)
    asyncio.run(run())


def test_remote_dataset_rejects_page_exceeding_declared_count(tmp_path, monkeypatch):
    import asyncio
    import pytest
    import grid.ml_agent_worker as agent

    monkeypatch.setenv("ProgramData", str(tmp_path))

    class Client:
        async def dataset_page(self, job, offset, limit):
            return {"sample_count": 1, "dataset_hash": "unused",
                    "dataset_id": "ds", "samples": [
                        {"payload": {"x": 1}, "payload_hash": "unused"},
                        {"payload": {"x": 2}, "payload_hash": "unused"}]}
        async def renew(self, job):
            return {"ok": True}

    async def run():
        with pytest.raises(ValueError, match="page exceeds remaining"):
            await agent._write_paged_bundle(Client(), {"id": "j"}, tmp_path / "bundle.json")

    asyncio.run(run())
