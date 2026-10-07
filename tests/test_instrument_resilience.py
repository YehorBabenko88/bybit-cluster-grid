from datetime import datetime,timezone,timedelta
from grid.instrument_resilience import feed_health,operational_state,requirements_met
from grid.live_assignment_policy import guarded_live_symbols

def test_missing_optional_feed_does_not_disable_instrument():
    now=datetime.now(timezone.utc)
    candle=feed_health(now,now=now,stale_after_s=10)
    trades=feed_health(now,now=now,stale_after_s=10)
    oi=feed_health(None,now=now)
    assert oi.state=="UNAVAILABLE"
    assert operational_state(listed=True,ohlcv=candle,trades=trades,
                             optional_feeds=(oi,),history_samples=100)=="ACTIVE"
    ok,missing=requirements_met(("ohlcv_history","open_interest"),
                                {"ohlcv_history":"READY","open_interest":"UNAVAILABLE"})
    assert not ok and missing==("open_interest",)

def test_required_feed_staleness_degrades_instrument():
    now=datetime.now(timezone.utc)
    stale=feed_health(now-timedelta(seconds=30),now=now,stale_after_s=10)
    live=feed_health(now,now=now,stale_after_s=10)
    assert operational_state(listed=True,ohlcv=stale,trades=live,history_samples=100)=="DEGRADED"

def test_new_instrument_must_warm_up():
    now=datetime.now(timezone.utc);live=feed_health(now,now=now)
    assert operational_state(listed=True,ohlcv=live,trades=live,history_samples=5,min_warmup_samples=60)=="WARMING_UP"

def test_delisted_instrument_is_retired():
    assert operational_state(listed=False,history_samples=100)=="RETIRED"

def test_stale_assignment_cannot_resurrect_delisted_symbol_after_reboot():
    out=guarded_live_symbols(market_enabled=True,install_mode="NORMAL",live_mode="NORMAL",
      node_assignments=["BTCUSDT","GONEUSDT"],instrument_symbols={"BTCUSDT":{}})
    assert out==["BTCUSDT"]
