import pytest
from grid.scientific_simulation import SimulationConfig,simulate_rows


def row(ts,symbol="BTCUSDT"):
    return {"symbol":symbol,"event_ts_ms":ts,"return_bps":12.0,
            "split_key":"2026-W40"}


def test_duplicate_symbol_and_timestamp_rejected():
    with pytest.raises(ValueError,match="duplicate simulated event"):
        simulate_rows([row(1000),row(1000)],1,60000,SimulationConfig())


def test_same_timestamp_different_symbols_are_independent():
    result=simulate_rows([row(1000),row(1000,"ETHUSDT")],1,60000,SimulationConfig())
    assert result["metrics"]["trades"]==2


def test_repeated_symbol_at_different_timestamps_is_valid():
    result=simulate_rows([row(1000),row(2000)],1,60000,SimulationConfig())
    assert result["metrics"]["trades"]==2
