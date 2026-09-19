from datetime import datetime,timedelta,timezone
from grid.rolling_event_features import RollingEventFeatures
from grid.instrument_profile import InstrumentProfile
from grid.ml_targets import breakout_target

def test_rolling_snapshot_excludes_event_row():
    r=RollingEventFeatures(); a=datetime(2026,1,1,tzinfo=timezone.utc)
    r.push("BTC",a,{"delta_ratio":1,"volume_ratio":1})
    r.push("BTC",a+timedelta(minutes=1),{"delta_ratio":2,"volume_ratio":2})
    x=r.snapshot("BTC",a+timedelta(minutes=2))
    assert x["pre_1m_delta_ratio_last"]==2
    assert x["pre_3m_samples"]==2

def test_instrument_profile_is_symbol_specific():
    p=InstrumentProfile()
    p.push("BTC",{"range_pct":.01,"spread":1})
    p.push("ETH",{"range_pct":.03,"spread":2})
    assert p.snapshot("BTC")["median_range_pct"]==.01
    assert p.snapshot("ETH")["median_range_pct"]==.03

def test_delayed_target_directionality():
    up=breakout_target(100,"UP",[{"high":105,"low":99,"close":104}])
    dn=breakout_target(100,"DOWN",[{"high":101,"low":95,"close":96}])
    assert up["mfe_pct"]==.05 and up["continuation_positive"]
    assert dn["mfe_pct"]==.05 and dn["continuation_positive"]
