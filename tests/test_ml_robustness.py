from grid.ml_robustness import robustness_suite
def test_robustness_reports_cost_stress_and_monte_carlo_drawdown():
    trades=[{"pnl":2.0,"fees":.1,"slippage":.1,"symbol":"BTC","regime":"HIGH_VOL","setup_type":"BREAKOUT","fold":1} for _ in range(30)]
    r=robustness_suite(trades)
    assert r["scenarios"]["base"]["overall"]["net_pnl"]>r["scenarios"]["combined"]["overall"]["net_pnl"]
    assert r["monte_carlo"]["runs"]==500
    assert "dd_p95" in r["monte_carlo"]
