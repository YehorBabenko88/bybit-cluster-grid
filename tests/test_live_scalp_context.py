from grid.live_scalp_context import LiveScalpAssembler

def test_live_scalp_requires_fresh_trade():
    a=LiveScalpAssembler(max_age_ms=1000)
    level={"price":100,"direction":1,"kind":"swing_high"}
    assert a.update("BTC",2000,"orderbook_snapshot",{"best_bid":99.9,"best_ask":100.1},level) is None

def test_live_scalp_uses_real_book_features_when_fresh():
    a=LiveScalpAssembler(max_age_ms=3000)
    level={"price":100,"direction":1,"kind":"swing_high"}
    a.update("BTC",1000,"orderbook_snapshot",{"best_bid":99.9,"best_ask":100.1,"imbalance":.4,
      "book_update_rate":20,"book_cancel_rate":5,"walls":[{"ratio":7,"replenishment_ratio":.5}]},None)
    x=a.update("BTC",1200,"trade_tape_250ms",{"close":99.8,"buy_volume":8,"sell_volume":2,"trade_count":7},level)
    assert x is not None
    assert x.features["book_imbalance"]==.4
    assert x.features["book_velocity"]==20
    assert x.features["wall_ratio"]==7
