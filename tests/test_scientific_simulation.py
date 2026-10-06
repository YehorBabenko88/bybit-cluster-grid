from grid.scientific_simulation import (
    SimulationConfig,simulate_rows,deterministic_bootstrap_drawdowns,promotion_decision)

def rows(n=120):
    out=[]
    for i in range(n):
        out.append({"symbol":"BTC" if i%2==0 else "ETH","event_ts_ms":i*70000,
          "split_key":f"W{1+i%4}","return_bps":6.0 if i%4 else -2.0})
    return out

def test_stress_execution_is_worse_than_base():
    cfg=SimulationConfig()
    base=simulate_rows(rows(),1,60000,cfg,1.0)["metrics"]
    stress=simulate_rows(rows(),1,60000,cfg,1.75)["metrics"]
    assert stress["expectancy_bps"]<base["expectancy_bps"]

def test_simulation_is_deterministic():
    cfg=SimulationConfig()
    assert simulate_rows(rows(20),1,5000,cfg)==simulate_rows(rows(20),1,5000,cfg)

def test_monte_carlo_is_deterministic():
    x=[4,-2,5,1,-1]*30
    assert deterministic_bootstrap_drawdowns(x,50,"x")==deterministic_bootstrap_drawdowns(x,50,"x")

def test_promotion_requires_independent_splits_and_symbols():
    cfg=SimulationConfig(min_trades=10)
    m=simulate_rows(rows(40),1,60000,cfg)["metrics"]
    stress=simulate_rows(rows(40),1,60000,cfg,1.75)["metrics"]
    mc=deterministic_bootstrap_drawdowns([4]*40,20,"x")
    passed,checks,_=promotion_decision(m,stress,mc,cfg)
    assert checks["independent_splits"] and checks["cross_symbol"]
    one=dict(m);one["splits"]=1
    assert not promotion_decision(one,stress,mc,cfg)[0]

def test_excessive_drawdown_blocks_promotion():
    cfg=SimulationConfig(min_trades=1,min_splits=1,min_symbols=1,min_expectancy_bps=-99,
      min_profit_factor=0,min_win_rate=0,max_single_split_share=1,monte_carlo_max_dd_p95=1)
    m={"trades":10,"splits":2,"symbols":2,"expectancy_bps":2,"profit_factor":2,
       "win_rate":.6,"max_drawdown":.5,"split_concentration":.5}
    stress=dict(m);stress["expectancy_bps"]=1;stress["profit_factor"]=1.2
    passed,checks,_=promotion_decision(m,stress,[.1],cfg)
    assert not passed and not checks["drawdown"]

def test_simulator_has_no_exchange_execution_dependency():
    from pathlib import Path
    s=Path("grid/scientific_simulation.py").read_text(encoding="utf-8")
    g=Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8")
    assert "place_order" not in s+g
    assert "pybit" not in s+g


def test_promotion_gate_is_strictly_oos_and_fail_closed():
    from pathlib import Path
    g=Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8")
    assert "max(dataset_cutoff)" in g
    assert "to_timestamp(event_ts_ms/1000.0)>$2" in g
    assert "WAITING_OOS" in g
    assert '"combinatorial-v1"' in g
