from grid.micro_tape import MicroTapeAggregator
from grid.models import Trade


def test_micro_tape_aggregates_aggressor_flow_and_cvd():
    a=MicroTapeAggregator(bucket_ms=250)
    assert a.add(Trade("BTCUSDT",1000,100.0,2.0,"Buy")) is None
    assert a.add(Trade("BTCUSDT",1100,99.5,1.0,"Sell")) is None

    closed=a.add(Trade("BTCUSDT",1250,100.5,3.0,"Buy"))

    assert closed["start_ms"]==1000
    assert closed["buy_volume"]==2.0
    assert closed["sell_volume"]==1.0
    assert closed["delta"]==1.0
    assert closed["cvd"]==1.0
    assert closed["trade_count"]==2
    assert closed["high"]==100.0
    assert closed["low"]==99.5


def test_micro_tape_cvd_is_continuous_across_buckets():
    a=MicroTapeAggregator(bucket_ms=250)
    a.add(Trade("ETHUSDT",1000,10.0,5.0,"Sell"))
    first=a.add(Trade("ETHUSDT",1250,10.1,2.0,"Buy"))
    second=a.add(Trade("ETHUSDT",1500,10.2,1.0,"Sell"))

    assert first["delta"]==-5.0
    assert first["cvd"]==-5.0
    assert second["delta"]==2.0
    assert second["cvd"]==-3.0
