from grid.cluster import FootprintBuilder
from grid.models import Trade
from grid.features import FeatureEngine

def trade(ts,price=100):
    return Trade(symbol="BTCUSDT",ts_ms=ts,price=price,qty=1,side="Buy")

def test_footprint_carries_degraded_quality():
    f=FootprintBuilder(1)
    f.add(trade(1000))
    f.mark_degraded("BTCUSDT",2000,"ws_reconnect")
    rows=f.pop_closed(61000)
    assert rows[0]["quality_status"]=="DEGRADED"
    assert "ws_reconnect" in rows[0]["quality_reasons"]

def test_degraded_candle_not_added_to_feature_baseline():
    e=FeatureEngine(lookback=10)
    good={"symbol":"BTC","open":100,"high":101,"low":99,"close":100,"buy_volume":5,"sell_volume":5,"delta":0,"poc_price":100,"quality_status":"GOOD"}
    bad=dict(good); bad["close"]=1000; bad["high"]=1001; bad["quality_status"]="DEGRADED"
    a=e.on_candle(good); b=e.on_candle(bad)
    assert a["eligible"] is True
    assert b["eligible"] is False
    assert len(e.hist["BTC"])==1

def test_reconnect_degrades_all_open_symbol_buckets_only():
    f=FootprintBuilder(1)
    f.add(Trade(symbol="BTCUSDT",ts_ms=1000,price=100,qty=1,side="Buy"))
    f.add(Trade(symbol="BTCUSDT",ts_ms=61000,price=101,qty=1,side="Buy"))
    f.add(Trade(symbol="ETHUSDT",ts_ms=61000,price=50,qty=1,side="Buy"))
    f.mark_open_degraded("BTCUSDT","ws_reconnect")
    rows=f.pop_closed(121000)
    btc=[r for r in rows if r["symbol"]=="BTCUSDT"]
    eth=[r for r in rows if r["symbol"]=="ETHUSDT"]
    assert len(btc)==2 and all(r["quality_status"]=="DEGRADED" for r in btc)
    assert all("ws_reconnect" in r["quality_reasons"] for r in btc)
    assert eth[0]["quality_status"]=="GOOD"
