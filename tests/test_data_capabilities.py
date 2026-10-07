from grid.data_capabilities import feature_permissions
def test_ohlcv_alone_never_claims_poc_delta_or_historical_orderbook():
    p=feature_permissions({"ohlcv_history":"READY","trade_history":"UNAVAILABLE",
      "footprint_history":"UNAVAILABLE","orderbook_history":"UNAVAILABLE"})
    assert p["volatility_history"] and p["htf_levels_history"]
    assert not p["poc_history"] and not p["delta_history"]
    assert not p["historical_orderbook_microstructure"]

def test_derivatives_capabilities_are_independent():
    p=feature_permissions({"ohlcv_history":"READY","live_derivatives":"LIVE",
      "open_interest":"UNAVAILABLE","funding_rate":"LIVE"})
    assert p["live_derivatives"]
    assert not p["open_interest"]
    assert p["funding_rate"]
