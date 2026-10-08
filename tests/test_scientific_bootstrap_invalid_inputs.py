import pytest

from grid.scientific_simulation import deterministic_bootstrap_drawdowns


@pytest.mark.parametrize("bad",[float("nan"),float("inf"),float("-inf")])
def test_bootstrap_rejects_nonfinite_trade_outcomes(bad):
    with pytest.raises(ValueError,match="finite"):
        deterministic_bootstrap_drawdowns([1.0,bad,-2.0],paths=10)


@pytest.mark.parametrize("bad",[float("nan"),float("inf"),-1.0])
def test_bootstrap_rejects_invalid_position_scale(bad):
    with pytest.raises(ValueError,match="position scale"):
        deterministic_bootstrap_drawdowns([1.0,-2.0],paths=10,position_scale=bad)


def test_bootstrap_is_reproducible_for_valid_returns():
    args=[1.0,-2.0,3.0,-1.0]
    a=deterministic_bootstrap_drawdowns(args,paths=16,seed="fixed")
    b=deterministic_bootstrap_drawdowns(args,paths=16,seed="fixed")
    assert a==b
    assert len(a)==16
    assert all(0<=x<=1 for x in a)
