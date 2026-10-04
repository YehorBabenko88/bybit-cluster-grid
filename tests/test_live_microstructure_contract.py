from grid.orderbook import analyze_book
from grid.book_velocity import BookVelocity
from grid.micro_tape import MicroTapeAggregator
from grid.models import Trade


def test_orderbook_exposes_multi_depth_metrics():
    bids=[(100.0-i, i+1.0) for i in range(50)]
    asks=[(101.0+i, i+1.0) for i in range(50)]
    x=analyze_book(bids,asks)
    assert x["bid_depth_1"]==1.0
    assert x["ask_depth_5"]==sum(i+1.0 for i in range(5))
    assert x["bid_depth_25"]==sum(i+1.0 for i in range(25))
    assert x["bid_depth_50"]==x["bid_depth"]


def test_book_velocity_keeps_side_specific_add_remove_amounts():
    v=BookVelocity()
    first=v.update("BTCUSDT",1000,{100.0:10.0},{101.0:8.0})
    assert first["added_bid"]==0.0
    x=v.update("BTCUSDT",2000,{100.0:13.0},{101.0:5.0,102.0:2.0})
    assert x["added_bid"]==3.0
    assert x["removed_ask"]==3.0
    assert x["added_ask"]==2.0


def test_micro_tape_preserves_seq_quality_and_causal_large_trade_state():
    a=MicroTapeAggregator(bucket_ms=250,large_trade_mult=2.0,ema_alpha=.5)
    a.add(Trade("BTCUSDT",1000,100.0,1.0,"Buy",seq=10))
    a.add(Trade("BTCUSDT",1100,100.1,3.0,"Buy",seq=11,continuity_gap=True))
    closed=a.add(Trade("BTCUSDT",1250,100.2,1.0,"Sell",seq=12))
    assert closed["first_seq"]==10
    assert closed["last_seq"]==11
    assert closed["large_buy_volume"]==3.0
    assert closed["trade_gap"] is True
    assert a.latest("BTCUSDT")["start_ms"]==1000
