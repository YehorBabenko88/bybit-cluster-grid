import math
from grid.scientific_event_router import _num


def test_nonfinite_market_values_do_not_enter_scientific_signals():
    for value in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", "-Infinity"):
        assert _num(value) is None
        assert _num(value, 0.0) == 0.0
    assert _num("1.25") == 1.25
    assert _num(None, 2.0) == 2.0
    assert _num(10 ** 10000) is None
