from grid.continuity import SequenceGuard,TradeContinuity

def test_book_sequence_accepts_noncontiguous_cross_seq_when_update_id_is_contiguous():
    g=SequenceGuard(); g.snapshot(100,10)
    assert g.delta(150,11)
    assert g.delta(999,12)
    assert g.valid and g.gaps==0

def test_book_update_id_gap_invalidates_until_snapshot():
    g=SequenceGuard(); g.snapshot(100,10)
    assert not g.delta(103,12)
    assert not g.valid and g.gaps==1
    assert g.last_reason=="update_id_gap"
    assert not g.delta(104,13)
    g.snapshot(200,20)
    assert g.delta(500,21)

def test_stale_update_is_rejected_without_destroying_valid_book():
    g=SequenceGuard(); g.snapshot(100,10)
    assert not g.delta(99,11)
    assert g.valid
    assert g.last_reason=="stale_seq"
    assert g.delta(101,11)
    assert not g.delta(102,11)
    assert g.valid
    assert g.last_reason=="stale_update_id"

def test_trade_continuity_marks_time_gap_without_claiming_missing_count():
    t=TradeContinuity(gap_ms=5000)
    assert not t.observe(1000)
    assert not t.observe(2000)
    assert t.observe(8001)
    assert t.suspect_gaps==1
    t.reconnect()
    assert t.reconnects==1
