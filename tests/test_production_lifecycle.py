from pathlib import Path
from dataclasses import FrozenInstanceError
import pytest
from grid.barrier_simulator import simulate_barrier
from grid.trade_plan import TradePlan,assert_plan_unchanged


def test_current_regime_taxonomy_is_consistent():
    h=Path("grid/historical_signal_source.py").read_text()
    v=Path("grid/historical_variant_engine.py").read_text()
    m=Path("grid/markov_strategy_context.py").read_text()
    for old in ("HIGH_VOL","IMPULSE","DECAY"):
        assert old not in h
        assert old not in v
        assert old not in m
    assert "EXPANDING" in h and "VOLATILE" in h


def test_barrier_uses_100_dollar_notional_and_fixed_levels():
    sig={"symbol":"BTCUSDT","setup_type":"POC","entry_ref":100.0,"direction":"LONG"}
    candles=[{"ts":1,"open":100.0,"high":100.5,"low":99.9,"close":100.4}]
    t=simulate_barrier(sig,candles,tp_bps=40,sl_bps=25,fee_bps=0,slippage_bps=0,notional=100)
    assert t["notional"]==100
    assert t["quantity"]==1
    assert t["initial_tp"]==pytest.approx(100.4)
    assert t["initial_sl"]==pytest.approx(99.75)
    assert t["pnl"]==pytest.approx(.4)


def test_trade_plan_is_immutable_and_fingerprinted():
    p=TradePlan("BTCUSDT","LONG",100,99.75,100.4,100)
    assert assert_plan_unchanged(p,p)
    with pytest.raises(FrozenInstanceError):
        p.stop_loss=100.0


def test_tailscale_bootstrap_is_unattended_and_does_not_persist_key():
    s=Path("installer/configure-tailscale.ps1").read_text()
    assert "--unattended=true" in s
    assert "Set-Content" not in s
    b=Path("installer/bootstrap.ps1").read_text()
    assert '$TailscaleAuthKey=""' in b
