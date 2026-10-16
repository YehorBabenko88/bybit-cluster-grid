import pytest

from grid.scheduler import weighted_assign


@pytest.mark.parametrize("invalid_costs", [["BTCUSDT"], "bad", 42, {"BTCUSDT"}])
def test_malformed_cost_mapping_does_not_abort_rebalance(invalid_costs):
    nodes = {"A": {"symbol_cost": invalid_costs}, "B": {"symbol_cost": {"BTCUSDT": 2}}}
    assigned = weighted_assign(["BTCUSDT"], {"A": 1, "B": 1}, nodes)
    assert sum("BTCUSDT" in symbols for symbols in assigned.values()) == 1


@pytest.mark.parametrize("invalid_drained", [{"x": 1}, [["BTCUSDT"]], [None], "BTCUSDT"])
def test_malformed_drained_symbols_does_not_abort_or_assign_to_pressured_node(invalid_drained):
    nodes = {"A": {"pressure_state": "REDUCE_LOAD", "drained_symbols": invalid_drained},
             "B": {"pressure_state": "NORMAL"}}
    assigned = weighted_assign(["BTCUSDT"], {"A": 10, "B": 1}, nodes)
    assert assigned == {"A": [], "B": ["BTCUSDT"]}
