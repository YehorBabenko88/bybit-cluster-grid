from grid.position_sizing_research import apply_sizing,ruin_stats
def test_capped_martingale_increases_after_losses_and_resets_after_win():
    x=apply_sizing([{"pnl":-1},{"pnl":-1},{"pnl":2},{"pnl":-1}],"MARTINGALE",max_size=4)
    assert [r["size_multiplier"] for r in x]==[1,2,4,1]
def test_ruin_stats_detect_deep_loss_path():
    assert ruin_stats([{"pnl":-60}],100,.5)["ruined"]
