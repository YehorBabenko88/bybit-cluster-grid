from grid.volatility_regime import VolatilityRegimeDetector,QUIET,EXPANDING,VOLATILE,EXHAUSTION

def f(rv=0.01,rng=0.01,vol=1.0):
    return {"realized_volatility":rv,"range_pct":rng,"volume_ratio":vol}

def test_regime_progression_with_hysteresis_thresholds():
    d=VolatilityRegimeDetector(lookback=20,min_history=3,confirm=1,min_dwell=0)
    for _ in range(3):
        assert d.update("BTC",f())["regime"]==QUIET
    assert d.update("BTC",f())["regime"]==QUIET
    assert d.update("BTC",f(.018,.018,1.5))["regime"]==EXPANDING
    assert d.update("BTC",f(.03,.03,2.2))["regime"]==VOLATILE
    assert d.update("BTC",f(.006,.006,.7))["regime"]==EXHAUSTION
    assert d.update("BTC",f(.004,.004,.5))["regime"]==QUIET

def test_degraded_sample_neither_trains_baseline_nor_changes_state():
    d=VolatilityRegimeDetector(lookback=20,min_history=2,confirm=1,min_dwell=0)
    d.update("ETH",f()); d.update("ETH",f())
    before=len(d.hist["ETH"])
    out=d.update("ETH",f(.5,.5,4),eligible=False)
    assert out["regime"]==QUIET
    assert len(d.hist["ETH"])==before

def test_regime_reports_warmup_readiness():
    d=VolatilityRegimeDetector(min_history=3)
    assert d.update("SOL",f())["regime_ready"] is False
    d.update("SOL",f()); d.update("SOL",f())
    assert d.update("SOL",f())["regime_ready"] is True
