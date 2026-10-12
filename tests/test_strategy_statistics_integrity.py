import pytest
from grid.strategy_statistics import paired_expectancy_bootstrap, block_bootstrap_expectancy


def trade(identifier, pnl):
    return {"signal_id": identifier, "pnl": pnl, "fees": 0, "slippage": 0}


def test_duplicate_paired_trade_ids_fail_closed():
    base = [trade("a", 1), trade("a", -100), trade("b", 2)]
    variant = [trade("a", 3), trade("b", 4)]
    with pytest.raises(ValueError, match="duplicate"):
        paired_expectancy_bootstrap(base, variant)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_pnl_rejected_in_both_bootstraps(invalid):
    with pytest.raises(ValueError, match="finite"):
        paired_expectancy_bootstrap([trade("a", invalid), trade("b", 1)],
                                    [trade("a", 1), trade("b", 1)])
    with pytest.raises(ValueError, match="finite"):
        block_bootstrap_expectancy([trade("a", invalid), trade("b", 1)], block_size=1)


@pytest.mark.parametrize("runs", [0, -1, True, 1.5])
def test_invalid_bootstrap_run_count_rejected(runs):
    with pytest.raises(ValueError):
        paired_expectancy_bootstrap([], [], runs=runs)
    with pytest.raises(ValueError):
        block_bootstrap_expectancy([], runs=runs)


def test_valid_paired_comparison_remains_deterministic():
    base = [trade("a", 1), trade("b", 2)]
    variant = [trade("a", 3), trade("b", 5)]
    assert paired_expectancy_bootstrap(base, variant, runs=50) == paired_expectancy_bootstrap(base, variant, runs=50)
