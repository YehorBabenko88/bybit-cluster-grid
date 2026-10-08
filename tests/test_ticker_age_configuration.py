import pytest

from grid.microstructure import MicrostructureCollector


@pytest.mark.parametrize("invalid",[0,-1,True,False,1.5,"300000",[],{}])
def test_invalid_ticker_age_setting_rejected(invalid):
    with pytest.raises(ValueError,match="max_ticker_age_ms"):
        MicrostructureCollector(None,max_ticker_age_ms=invalid)


@pytest.mark.parametrize("valid",[None,1,300000])
def test_valid_ticker_age_setting_accepted(valid):
    collector=MicrostructureCollector(None,max_ticker_age_ms=valid)
    assert collector.max_ticker_age_ms==valid
