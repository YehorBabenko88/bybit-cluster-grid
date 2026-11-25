from market_data.history_planning import declare_history_instrument,plan_history_requests

def test_instrument_history_plan_starts_at_launch_and_uses_dataset_cadence():
    inst={'symbol':'BTCUSDT','launchTime':'1','fundingInterval':'480'}
    reqs={r.dataset:r for r in plan_history_requests(declare_history_instrument(inst),end_ms=1_000_000).requests}
    assert reqs['candles'].start_ms==60_000 and reqs['candles'].timeframe=='1m'
    assert reqs['mark_price'].timeframe=='1m'
    assert reqs['open_interest'].timeframe=='5m'
    assert 'funding' not in reqs  # requested horizon contains no complete 480m funding bucket
    assert reqs['long_short_ratio'].timeframe=='5m'
