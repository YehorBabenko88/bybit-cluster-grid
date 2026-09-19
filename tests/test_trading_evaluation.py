from grid.trading_evaluation import evaluate_trades,stability_summary
def test_evaluation_exposes_segment_failure_instead_of_hiding_in_aggregate():
    rows=[]
    for i in range(25):
        rows.append({"pnl":2,"mfe":3,"mae":-1,"symbol":"BTC","regime":"HIGH_VOL","setup_type":"POC","fold":1})
        rows.append({"pnl":-1,"mfe":1,"mae":-2,"symbol":"ETH","regime":"HIGH_VOL","setup_type":"POC","fold":1})
    r=evaluate_trades(rows);s=stability_summary(r,min_trades=20)
    assert r["overall"]["net_pnl"]>0
    assert r["symbol"]["ETH"]["expectancy"]<0
    assert s["positive_fraction"]<1
