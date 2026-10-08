import math

import pytest

from grid.continuity import SequenceGuard


@pytest.mark.parametrize("bad",[math.inf,-math.inf,float("nan")])
def test_invalid_snapshot_sequence_is_rejected_without_exception(bad):
    guard=SequenceGuard()
    assert guard.snapshot(bad,1) is False
    assert guard.valid is False
    assert guard.snapshot(1,bad) is False


@pytest.mark.parametrize("bad",[math.inf,-math.inf,float("nan")])
def test_invalid_delta_sequence_invalidates_book_without_exception(bad):
    guard=SequenceGuard()
    assert guard.snapshot(1,1) is True
    assert guard.delta(bad,2) is False
    assert guard.valid is False
    assert guard.snapshot(3,3) is True
    assert guard.delta(4,bad) is False
    assert guard.valid is False
