import pytest

from grid.continuity import SequenceGuard


@pytest.mark.parametrize("bad",[True,False,1.5,"1.5","1e3"," 1 ","+1",[],{}])
def test_snapshot_rejects_noninteger_metadata(bad):
    guard=SequenceGuard()
    assert guard.snapshot(bad,1) is False
    assert guard.valid is False
    assert guard.snapshot(1,bad) is False


@pytest.mark.parametrize("bad",[True,False,2.5,"2.5","2e3"," 2 ","+2"])
def test_delta_rejects_noninteger_metadata(bad):
    guard=SequenceGuard()
    assert guard.snapshot(1,1)
    assert guard.delta(bad,2) is False
    assert guard.valid is False
    assert guard.snapshot(1,1)
    assert guard.delta(2,bad) is False
    assert guard.valid is False


def test_valid_numeric_strings_and_integer_metadata_are_accepted():
    guard=SequenceGuard()
    assert guard.snapshot("10","20")
    assert guard.delta(11,"21")
    assert guard.last_seq==11
    assert guard.last_update==21
