from datetime import datetime,timedelta,timezone
from grid.historical_levels import HistoricalLevelTracker,FIRST_CROSS,FALSE_BREAK,ACCEPTED_BREAK,RETEST_HOLD
from grid.book_velocity import BookVelocity

def test_first_cross_freezes_prebreak_features_then_false_break():
    t=HistoricalLevelTracker(accept_bars=2,false_break_bars=3)
    a=datetime(2026,1,1,tzinfo=timezone.utc)
    x=t.register("BTC","D","HIGH",a,100,"RESISTANCE")
    t.observe("BTC",a+timedelta(minutes=1),98,99.9,97,99.8,{"delta_ratio":.1})
    ev=t.observe("BTC",a+timedelta(minutes=2),99.8,102,99.7,101,{"delta_ratio":.5})
    cross=[e for e in ev if e[0]==FIRST_CROSS][0]
    assert cross[2]["pre_features"]["delta_ratio"]==.1
    ev=t.observe("BTC",a+timedelta(minutes=3),101,101.2,98.5,99,{"delta_ratio":-.4})
    assert any(e[0]==FALSE_BREAK for e in ev)

def test_accepted_break_and_retest_hold():
    t=HistoricalLevelTracker(accept_bars=2)
    a=datetime(2026,1,1,tzinfo=timezone.utc)
    t.register("BTC","W","HIGH",a,100,"RESISTANCE")
    t.observe("BTC",a+timedelta(minutes=1),99,101,98,99.5,{})
    t.observe("BTC",a+timedelta(minutes=2),99.5,102,99,101,{})
    t.observe("BTC",a+timedelta(minutes=3),101,103,100.5,102,{})
    ev=t.observe("BTC",a+timedelta(minutes=4),102,103,100.5,102,{})
    assert any(e[0]==ACCEPTED_BREAK for e in ev)
    ev=t.observe("BTC",a+timedelta(minutes=5),102,102.5,99.99,101,{})
    assert any(e[0]==RETEST_HOLD for e in ev)

def test_book_velocity_measures_changes_not_fake_consumption():
    v=BookVelocity()
    assert v.update("BTC",1000,{99:10},{101:10})["book_update_rate"] is None
    x=v.update("BTC",2000,{99:12},{101:5,102:4})
    assert x["book_update_rate"]==3
    assert x["book_add_rate"]==6
    assert x["book_cancel_rate"]==5
    assert x["book_consume_rate"] is None
