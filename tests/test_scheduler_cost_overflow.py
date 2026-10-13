from grid.scheduler import learned_symbol_cost, weighted_assign


def test_oversized_integer_symbol_cost_does_not_abort_fleet_assignment():
    # A JSON integer may be valid while exceeding float's finite range.
    nodes = {
        "A": {"symbol_cost": {"BTCUSDT": 10**400}},
        "B": {"symbol_cost": {"BTCUSDT": 7}},
    }
    costs, fallback = learned_symbol_cost(nodes)
    assert costs == {"BTCUSDT": 7}
    assert fallback == 7
    assignments = weighted_assign(["BTCUSDT"], {"A": 1, "B": 1}, nodes)
    assert assignments == {"A": ["BTCUSDT"], "B": []}
