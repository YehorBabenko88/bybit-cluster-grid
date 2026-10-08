from grid.continuity import SequenceGuard,TradeContinuity

def test_book_sequence_accepts_contiguous_updates():
    g=SequenceGuard(); g.snapshot(100,10)
    assert g.delta(101,11)
    assert g.delta(102,12)
    assert g.valid and g.gaps==0

def test_book_cross_sequence_can_jump_forward_without_false_gap():
    g=SequenceGuard(); g.snapshot(100,10)
    assert g.delta(103,11)
    assert g.delta(1000,12)
    assert g.valid and g.gaps==0


def test_book_backward_sequence_invalidates_until_snapshot():
    g=SequenceGuard(); g.snapshot(100,10)
    assert not g.delta(99,11)
    assert not g.valid and g.gaps==1
    assert not g.delta(104,12)
    g.snapshot(200,20)
    assert g.delta(201,21)

def test_stale_update_invalidates_book():
    g=SequenceGuard(); g.snapshot(100,10)
    assert not g.delta(101,10)
    assert not g.valid

def test_trade_continuity_marks_time_gap_without_claiming_missing_count():
    t=TradeContinuity(gap_ms=5000)
    assert not t.observe(1000)
    assert not t.observe(2000)
    assert t.observe(8001)
    assert t.suspect_gaps==1
    t.reconnect()
    assert t.reconnects==1
