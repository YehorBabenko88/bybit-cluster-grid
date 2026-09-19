from grid.incremental_edge import compare_variant,paired_signal_effect
def test_incremental_edge_shows_what_filter_removed():
    base=[{"signal_id":1,"pnl":-2},{"signal_id":2,"pnl":3},{"signal_id":3,"pnl":4}]
    variant=[{"signal_id":2,"pnl":3},{"signal_id":3,"pnl":4}]
    x=compare_variant(base,variant);p=paired_signal_effect(base,variant)
    assert x["signals_removed"]==1 and x["delta_expectancy"]>0
    assert p["removed"]["net_pnl"]<0 and p["kept_from_base"]["net_pnl"]>0
