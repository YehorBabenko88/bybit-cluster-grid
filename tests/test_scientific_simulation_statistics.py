import math
from grid.scientific_simulation import SimulationConfig,simulate_rows


def row(ts,ret):
    return {"symbol":"BTCUSDT","event_ts_ms":ts,"return_bps":ret,"split_key":"2026-W40"}


def test_simulation_reports_costs_uncertainty_and_losing_streak():
    result=simulate_rows([row(1000,100),row(2000,-100),row(3000,-100),
                          row(4000,100)],1,60000,SimulationConfig())
    metrics=result["metrics"]
    assert metrics["trades"]==4
    assert metrics["expectancy_standard_error_bps"]>0
    assert math.isfinite(metrics["expectancy_lower_95_bps"])
    assert metrics["expectancy_lower_95_bps"]<metrics["expectancy_bps"]
    assert metrics["max_consecutive_nonwinning_trades"]==2
    for component in ("fee","spread","slippage","latency","funding"):
        expected=sum(t[f"{component}_bps"]*t["fill_fraction"] for t in result["trades"])
        assert math.isclose(metrics[f"total_{component}_bps"],expected)


def test_single_trade_does_not_invent_confidence_interval():
    result=simulate_rows([row(1000,5)],1,1000,SimulationConfig())
    assert result["metrics"]["expectancy_standard_error_bps"] is None
    assert result["metrics"]["expectancy_lower_95_bps"] is None
