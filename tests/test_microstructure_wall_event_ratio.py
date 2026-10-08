import math

import pytest

from grid.microstructure import MicrostructureCollector


@pytest.mark.parametrize("invalid",[0,-1,True,False,float("nan"),float("inf"),-float("inf"),"6",None,[],{}])
def test_invalid_wall_event_ratio_rejected(invalid):
    with pytest.raises(ValueError,match="wall_event_ratio"):
        MicrostructureCollector(None,wall_event_ratio=invalid)


@pytest.mark.parametrize("valid",[0.5,1,6.0,100])
def test_positive_finite_wall_event_ratio_accepted(valid):
    collector=MicrostructureCollector(None,wall_event_ratio=valid)
    assert collector.wall_event_ratio==valid
