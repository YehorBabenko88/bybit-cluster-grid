import pytest
from grid.scientific_simulation import SimulationConfig,simulate_rows


def row(ts,ret,symbol="BTCUSDT"):
    return {"symbol":symbol,"event_ts_ms":ts,"return_bps":ret,"split_key":"2026-W40"}


@pytest.mark.parametrize("bad",[float("nan"),float("inf"),float("-inf")])
def test_simulator_rejects_nonfinite_outcomes(bad):
    with pytest.raises(ValueError,match="finite"):
        simulate_rows([row(1000,bad)],1,1000,SimulationConfig())


def test_simulator_rejects_reverse_time_order():
    with pytest.raises(ValueError,match="chronological"):
        simulate_rows([row(2000,1),row(1000,2)],1,1000,SimulationConfig())


def test_simulator_accepts_equal_time_different_symbols():
    result=simulate_rows([row(1000,5),row(1000,-5,"ETHUSDT")],1,1000,SimulationConfig())
    assert result["metrics"]["trades"]==2


@pytest.mark.parametrize("direction",[0,2,-2,True])
def test_simulator_rejects_invalid_directions(direction):
    with pytest.raises(ValueError,match="direction"):
        simulate_rows([row(1000,1)],direction,1000,SimulationConfig())


@pytest.mark.parametrize("stress",[0,-1,float("nan"),float("inf")])
def test_simulator_rejects_invalid_stress(stress):
    with pytest.raises(ValueError,match="stress"):
        simulate_rows([row(1000,1)],1,1000,SimulationConfig(),stress)
