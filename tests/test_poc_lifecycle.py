from datetime import datetime,timedelta,timezone
from grid.poc_lifecycle import PocLifecycleTracker,NAKED,TOUCHED,CROSSED,ACCEPTED
from grid.setup_flags import setup_flags

def test_next_bar_open_at_previous_poc_is_first_touch():
    t=PocLifecycleTracker(tolerance_pct=.0001)
    a=datetime(2026,1,1,tzinfo=timezone.utc)
    x=t.register("BTC",a,100,101)
    ev=t.observe("BTC",a+timedelta(minutes=1),100,102,99,101)
    assert x.first_touch_minutes==1 and x.first_touch_kind=="OPEN_AT_POC"
    assert x.touch_count==1

def test_naked_poc_can_remain_unreturned_at_horizon():
    t=PocLifecycleTracker(tolerance_pct=.0001)
    a=datetime(2026,1,1,tzinfo=timezone.utc)
    x=t.register("BTC",a,100,100)
    for n in range(1,6): t.observe("BTC",a+timedelta(minutes=n),110,112,108,111)
    h=t.horizons("BTC",a+timedelta(minutes=5))
    assert x.status==NAKED and h[0]["returned"] is False

def test_acceptance_is_stricter_than_single_wick():
    t=PocLifecycleTracker(tolerance_pct=.001,accept_bars=2)
    a=datetime(2026,1,1,tzinfo=timezone.utc)
    x=t.register("BTC",a,100,100)
    t.observe("BTC",a+timedelta(minutes=1),102,103,99.95,102)
    assert x.status==TOUCHED and x.acceptance_ts is None
    t.observe("BTC",a+timedelta(minutes=2),101,101,99.9,100.05)
    t.observe("BTC",a+timedelta(minutes=3),100.1,101,99.9,100.02)
    assert x.status==ACCEPTED

def test_breakout_flags_require_regime_quality_and_flow():
    f={"breakout_up":True,"breakout_down":False,"volume_ratio":1.5,"delta_ratio":.3,
       "book_imbalance":.4,"close_vs_poc":.002}
    assert setup_flags(f,"VOLATILE",True)["breakout_long_candidate"]
    assert not setup_flags(f,"QUIET",True)["breakout_long_candidate"]
    assert not setup_flags(f,"VOLATILE",False)["breakout_long_candidate"]
