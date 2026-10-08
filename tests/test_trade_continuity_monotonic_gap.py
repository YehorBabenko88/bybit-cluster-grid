from grid.continuity import TradeContinuity


def test_late_trades_do_not_rewind_gap_baseline():
    continuity=TradeContinuity(gap_ms=5000)
    assert continuity.observe(10000) is False
    assert continuity.observe(9000) is False
    assert continuity.last_ts==10000
    assert continuity.observe(14999) is False
    assert continuity.suspect_gaps==0
    assert continuity.observe(20001) is True
    assert continuity.suspect_gaps==1


def test_duplicate_and_out_of_order_trades_do_not_count_gaps():
    continuity=TradeContinuity(gap_ms=5000)
    assert continuity.observe(10000) is False
    assert continuity.observe(10000) is False
    assert continuity.observe(100) is False
    assert continuity.observe(15001) is True
    assert continuity.observe(1000) is False
    assert continuity.suspect_gaps==1
    assert continuity.last_ts==15001


def test_invalid_timestamps_do_not_fabricate_gap_or_change_baseline():
    continuity=TradeContinuity(gap_ms=5000)
    assert continuity.observe(10000) is False
    for invalid in (None,False,0,-1,"garbled","1.5",1.5):
        assert continuity.observe(invalid) is False
        assert continuity.last_ts==10000
    assert continuity.observe(15000) is False
    assert continuity.suspect_gaps==0
