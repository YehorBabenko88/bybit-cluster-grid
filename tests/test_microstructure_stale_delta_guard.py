from grid.continuity import SequenceGuard


def test_old_delta_replay_is_stale_without_mutating_guard():
    guard=SequenceGuard()
    assert guard.snapshot(100,10)
    assert guard.is_stale_delta(99,9)
    assert guard.valid
    assert guard.last_seq==100
    assert guard.last_update==10
    assert guard.delta(101,11)


def test_mixed_ordering_or_invalid_metadata_not_classified_as_stale():
    guard=SequenceGuard()
    assert guard.snapshot(100,10)
    for seq,update in [(101,9),(99,11),(None,9),(99,None),(True,9),(-1,9)]:
        assert not guard.is_stale_delta(seq,update)
    assert guard.valid


def test_uninitialized_guard_does_not_suppress_delta():
    guard=SequenceGuard()
    assert not guard.is_stale_delta(10,2)
