import asyncio
import time

import pytest

import grid.server_pilot as server_pilot


class FakePool:
    def __init__(self, blocking=None):
        self.blocking = blocking

    async def fetchrow(self, query, *args):
        if "fleet_operations" in query:
            return self.blocking
        raise AssertionError(query)


def run(coro):
    return asyncio.run(coro)


def healthy_node(**overrides):
    node = {
        "last_seen": time.time(),
        "integrity_ok": True,
        "operator_stopped": True,
        "wanted_symbols": 0,
        "active_trade_streams": 0,
    }
    node.update(overrides)
    return node


def install_mocks(monkeypatch, *, install_mode="PILOT", gate="STOPPED",
                  state=None):
    state = state or {
        "node_id": "PC4",
        "mode": "PILOT_BOOTSTRAP",
        "phase": "WAITING",
        "paused": True,
        "progress": 0,
        "details": "{}",
    }
    writes = []

    async def fake_registered(pool, node_id):
        return install_mode

    async def fake_gate(pool):
        return {"state": gate}

    async def fake_state(pool, node_id):
        return dict(state)

    async def fake_update(pool, node_id, **kwargs):
        writes.append((node_id, kwargs))

    monkeypatch.setattr(server_pilot, "registered_install_mode", fake_registered)
    monkeypatch.setattr(server_pilot, "runtime_state", fake_gate)
    monkeypatch.setattr(server_pilot, "pilot_state", fake_state)
    monkeypatch.setattr(server_pilot, "update_pilot", fake_update)
    return writes


def test_clean_pilot_transition_is_guarded_and_does_not_open_global_gate(monkeypatch):
    writes = install_mocks(monkeypatch)
    pool = FakePool()
    result = run(server_pilot.begin_server_pilot_validation(
        pool, "PC4", {"PC4": healthy_node()}, 10
    ))
    assert result["mode"] == "PILOT_BOOTSTRAP"  # fake post-read
    assert len(writes) == 1
    node_id, update = writes[0]
    assert node_id == "PC4"
    assert update["mode"] == "PILOT_VALIDATING"
    assert update["phase"] == "LIVE_CANARY"
    assert update["paused"] is False
    assert update["progress"] == 90.0
    assert update["details"]["server_controlled_validation"] is True
    assert update["details"]["legacy_runner"] is False


@pytest.mark.parametrize("mode", ["UNKNOWN", "NORMAL"])
def test_non_pilot_role_is_rejected(monkeypatch, mode):
    writes = install_mocks(monkeypatch, install_mode=mode)
    with pytest.raises(ValueError, match="not server-authorized PILOT"):
        run(server_pilot.begin_server_pilot_validation(
            FakePool(), "PC4", {"PC4": healthy_node()}, 10
        ))
    assert writes == []


def test_global_active_is_rejected(monkeypatch):
    writes = install_mocks(monkeypatch, gate="ACTIVE")
    with pytest.raises(ValueError, match="global runtime must be STOPPED"):
        run(server_pilot.begin_server_pilot_validation(
            FakePool(), "PC4", {"PC4": healthy_node()}, 10
        ))
    assert writes == []


@pytest.mark.parametrize(
    "node, message",
    [
        (healthy_node(integrity_ok=False), "integrity"),
        (healthy_node(operator_stopped=False), "operator-stopped"),
        (healthy_node(wanted_symbols=1), "wanted symbols"),
        (healthy_node(active_trade_streams=1), "active trade streams"),
    ],
)
def test_unsafe_node_state_is_rejected(monkeypatch, node, message):
    writes = install_mocks(monkeypatch)
    with pytest.raises(ValueError, match=message):
        run(server_pilot.begin_server_pilot_validation(
            FakePool(), "PC4", {"PC4": node}, 10
        ))
    assert writes == []


def test_blocking_fleet_operation_is_rejected(monkeypatch):
    writes = install_mocks(monkeypatch)
    pool = FakePool({"action": "RESUME", "status": "RUNNING"})
    with pytest.raises(ValueError, match="fleet operation blocks"):
        run(server_pilot.begin_server_pilot_validation(
            pool, "PC4", {"PC4": healthy_node()}, 10
        ))
    assert writes == []


def test_invalid_lifecycle_is_rejected(monkeypatch):
    writes = install_mocks(
        monkeypatch,
        state={
            "node_id": "PC4",
            "mode": "READY_FOR_EXPANSION",
            "phase": "COMPLETE",
            "paused": False,
            "progress": 100,
            "details": {},
        },
    )
    with pytest.raises(ValueError, match="cannot enter validation"):
        run(server_pilot.begin_server_pilot_validation(
            FakePool(), "PC4", {"PC4": healthy_node()}, 10
        ))
    assert writes == []
