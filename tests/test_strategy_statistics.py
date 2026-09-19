from grid.strategy_statistics import paired_expectancy_bootstrap,block_bootstrap_expectancy
def test_paired_bootstrap_reports_supported_positive_delta():
    base=[{"signal_id":i,"pnl":0} for i in range(40)]
    variant=[{"signal_id":i,"pnl":1} for i in range(40)]
    r=paired_expectancy_bootstrap(base,variant,runs=200)
    assert r["paired"]==40 and r["positive_supported"] and r["ci95"][0]>0
def test_block_bootstrap_preserves_local_dependence_chunks():
    rows=[{"pnl":1 if i%10<7 else -1} for i in range(100)]
    r=block_bootstrap_expectancy(rows,block_size=10,runs=100)
    assert r["blocks"]==10 and r["ci95"] is not None
