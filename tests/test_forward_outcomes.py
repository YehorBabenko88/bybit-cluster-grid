import math
import pytest
from grid.forward_outcomes import ForwardOutcomeLedger

def test_outcomes_do_not_mature_early():
    q=ForwardOutcomeLedger((1,5))
    q.register("e1","BTCUSDT",1000,100.0,"micro",{"agent":"oi"})
    assert q.observe("BTCUSDT",1999,101.0)==[]
    x=q.observe("BTCUSDT",2000,101.0)
    assert len(x)==1 and x[0]["horizon_ms"]==1000
    assert q.pending_count()==1

def test_outcome_uses_first_observation_at_or_after_horizon():
    q=ForwardOutcomeLedger((1,))
    q.register("e1","BTCUSDT",1000,100.0,"micro")
    x=q.observe("BTCUSDT",2500,102.0)
    assert x[0]["label_ts_ms"]==2500
    assert math.isclose(x[0]["log_return"],math.log(1.02))

def test_symbols_are_isolated():
    q=ForwardOutcomeLedger((1,))
    q.register("e1","BTCUSDT",0,100.0,"micro")
    assert q.observe("ETHUSDT",2000,200.0)==[]
    assert q.pending_count()==1

def test_payload_is_snapshot_and_capacity_fails_closed():
    p={"score":3};q=ForwardOutcomeLedger((1,),max_pending=1)
    q.register("e","BTCUSDT",0,100,"micro",p);p["score"]=99
    with pytest.raises(BufferError):q.register("x","BTCUSDT",0,100,"micro")
    assert q.observe("BTCUSDT",1000,100)[0]["payload"]["score"]==3
