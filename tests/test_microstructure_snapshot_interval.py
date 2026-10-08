import pytest

from grid.microstructure import MicrostructureCollector


@pytest.mark.parametrize("invalid",[0,-1,True,False,1.5,"1000",None,[],{}])
def test_invalid_snapshot_interval_rejected(invalid):
    with pytest.raises(ValueError,match="snapshot_ms"):
        MicrostructureCollector(None,snapshot_ms=invalid)


@pytest.mark.parametrize("valid",[1,1000,60000])
def test_positive_integer_snapshot_interval_accepted(valid):
    collector=MicrostructureCollector(None,snapshot_ms=valid)
    assert collector.snapshot_ms==valid
