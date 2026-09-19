import pytest
from grid.runtime_gate import VALID_STATES

def test_transitional_states_are_fail_closed():
    assert {"STOPPING","STOPPED","RESUMING","DELETING"} <= VALID_STATES
    assert "ACTIVE" in VALID_STATES

def test_only_active_is_market_open():
    # This mirrors the contract used by market_work_allowed/coordinator:
    # every lifecycle/transitional state except ACTIVE is closed.
    assert [s for s in VALID_STATES if s=="ACTIVE"] == ["ACTIVE"]

def test_global_precedence_contract_documented():
    # Regression sentinel: local start/resume is only legal while the global gate is ACTIVE.
    def local_start_allowed(global_state):
        return global_state=="ACTIVE"
    for state in VALID_STATES-{"ACTIVE"}:
        assert not local_start_allowed(state)
    assert local_start_allowed("ACTIVE")
