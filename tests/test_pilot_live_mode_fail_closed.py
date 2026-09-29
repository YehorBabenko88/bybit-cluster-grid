import asyncio

from grid.pilot_state import node_accepts_live_assignments, node_live_mode


class FakePool:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, node_id):
        return self.row


def run(coro):
    return asyncio.run(coro)


def test_missing_pilot_state_is_fail_closed():
    pool = FakePool(None)

    assert run(node_live_mode(pool, "pilot-node")) == "PAUSED"
    assert run(node_accepts_live_assignments(pool, "pilot-node")) is False


def test_paused_node_is_fail_closed():
    pool = FakePool({"mode": "NORMAL", "paused": True})

    assert run(node_live_mode(pool, "pilot-node")) == "PAUSED"
    assert run(node_accepts_live_assignments(pool, "pilot-node")) is False


def test_explicit_normal_node_accepts_live_assignments():
    pool = FakePool({"mode": "NORMAL", "paused": False})

    assert run(node_live_mode(pool, "normal-node")) == "NORMAL"
    assert run(node_accepts_live_assignments(pool, "normal-node")) is True


def test_pilot_validating_does_not_accept_normal_assignments():
    pool = FakePool({"mode": "PILOT_VALIDATING", "paused": False})

    assert run(node_live_mode(pool, "pilot-node")) == "PILOT_VALIDATING"
    assert run(node_accepts_live_assignments(pool, "pilot-node")) is False


def test_unknown_persisted_mode_is_fail_closed():
    pool = FakePool({"mode": "BROKEN_MODE", "paused": False})

    assert run(node_live_mode(pool, "pilot-node")) == "PAUSED"
    assert run(node_accepts_live_assignments(pool, "pilot-node")) is False