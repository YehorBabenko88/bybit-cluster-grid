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


def test_dataset_pagination_rejects_changed_metadata(tmp_path):
    import asyncio
    import hashlib
    import json
    import pytest
    from grid.ml_agent_worker import _write_paged_bundle

    rows = [{"x": 1}, {"x": 2}]
    hashes = [hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest() for row in rows]
    digest = hashlib.sha256("\n".join(hashes).encode()).hexdigest()

    class Client:
        async def dataset_page(self, job, offset, limit):
            return {"dataset_id": "dataset-A" if offset == 0 else "dataset-B",
                    "dataset_hash": digest, "sample_count": 2, "feature_version": "v1",
                    "samples": [{"payload": rows[offset], "payload_hash": hashes[offset]}]}
        async def renew(self, job):
            return {"ok": True}

    async def scenario():
        with pytest.raises(ValueError, match="metadata changed"):
            await _write_paged_bundle(Client(), {"id": "job"}, tmp_path / "bundle.json", page_size=1)

    asyncio.run(scenario())


def test_dataset_transfer_rejects_empty_dataset(tmp_path):
    import asyncio
    import pytest
    from grid.ml_agent_worker import _write_paged_bundle

    class Client:
        async def dataset_page(self, job, offset, limit):
            return {"dataset_id": "ds", "dataset_hash": "unused",
                    "sample_count": 0, "samples": []}

    async def scenario():
        with pytest.raises(ValueError, match="sample count must be positive"):
            await _write_paged_bundle(Client(), {"id": "job"}, tmp_path / "empty.json")

    asyncio.run(scenario())


def test_dataset_transfer_rejects_zero_page_size(tmp_path):
    import asyncio
    import pytest
    from grid.ml_agent_worker import _write_paged_bundle

    class Client:
        async def dataset_page(self, job, offset, limit):
            pytest.fail("invalid page size must be rejected before remote request")

    async def scenario():
        with pytest.raises(ValueError, match="page size must be positive"):
            await _write_paged_bundle(Client(), {"id": "job"}, tmp_path / "bad.json", page_size=0)

    asyncio.run(scenario())


def test_ml_resource_limits_never_exceed_operator_caps(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import grid.ml_agent_worker as agent

    monkeypatch.setattr(agent, "settings", SimpleNamespace(
        ml_job_timeout_seconds=30, ml_job_ram_limit_mb=128
    ))
    assert agent._resource_limits({"timeout_seconds": 3600, "ram_limit_mb": 4096}) == (30, 128)
    assert agent._resource_limits({"timeout_seconds": 10, "ram_limit_mb": 64}) == (10, 64)
    with pytest.raises(ValueError, match="must be positive"):
        agent._resource_limits({"timeout_seconds": 0})
    with pytest.raises(ValueError, match="must be positive"):
        agent._resource_limits({"ram_limit_mb": -1})


def test_ml_compute_requires_fresh_lease_after_dataset(tmp_path, monkeypatch):
    import asyncio
    import pytest
    import grid.ml_agent_worker as agent

    monkeypatch.setenv("ProgramData", str(tmp_path))
    async def fake_bundle(client, job, path):
        path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(agent, "_write_paged_bundle", fake_bundle)

    class Client:
        async def renew(self, job):
            return None

    async def scenario():
        with pytest.raises(RuntimeError, match="lease lost before compute"):
            await agent.execute_remote_job(Client(), {"job_type": "train", "payload": {}})

    asyncio.run(scenario())
