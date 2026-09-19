from datetime import datetime,timezone,timedelta
from grid.level_generator import HistoricalLevelGenerator,_period

def candle(ts,h,l):
    return {"symbol":"BTC","ts":ts,"open":100,"high":h,"low":l,"close":100}

def test_hour_level_emitted_only_after_hour_is_complete():
    g=HistoricalLevelGenerator(("1H",))
    a=datetime(2026,1,1,10,0,tzinfo=timezone.utc)
    assert g.on_candle(candle(a,101,99))==[]
    assert g.on_candle(candle(a+timedelta(minutes=59),105,97))==[]
    out=g.on_candle(candle(a+timedelta(hours=1),103,98))
    assert {x.kind:x.price for x in out}=={"HIGH":105.0,"LOW":97.0}
    assert all(x.available_ts==a+timedelta(hours=1) for x in out)

def test_week_month_year_boundaries_are_utc_and_calendar_correct():
    sun=datetime(2026,9,20,23,59,tzinfo=timezone.utc)
    ws,we=_period(sun,"1W")
    assert ws.weekday()==0 and we-ws==timedelta(days=7)
    dec=datetime(2026,12,31,23,59,tzinfo=timezone.utc)
    ms,me=_period(dec,"1M"); ys,ye=_period(dec,"1Y")
    assert me==datetime(2027,1,1,tzinfo=timezone.utc)
    assert ye==datetime(2027,1,1,tzinfo=timezone.utc)

def test_h4_alignment():
    ts=datetime(2026,1,1,7,31,tzinfo=timezone.utc)
    s,e=_period(ts,"4H")
    assert s.hour==4 and e.hour==8
