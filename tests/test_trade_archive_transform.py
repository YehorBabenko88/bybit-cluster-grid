from datetime import datetime,timezone
from grid.trade_archive_transform import aggregate_minute
def test_archive_trade_aggregation_builds_delta_and_volume_poc_from_executions():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    trades=[{"ts":t,"price":100.0,"size":2,"side":"Buy","trade_id":"1"},
            {"ts":t,"price":100.0,"size":1,"side":"Sell","trade_id":"2"},
            {"ts":t,"price":101.0,"size":1,"side":"Buy","trade_id":"3"}]
    x=aggregate_minute("BTCUSDT",trades,.5)[0]
    assert x["delta"]==2 and x["poc_price"]==100.0 and x["trade_count"]==3
