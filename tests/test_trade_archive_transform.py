from datetime import datetime,timezone
from grid.trade_archive_transform import aggregate_minute
def test_archive_trade_aggregation_builds_delta_and_volume_poc_from_executions():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    trades=[{"ts":t,"price":100.0,"size":2,"side":"Buy","trade_id":"1"},
            {"ts":t,"price":100.0,"size":1,"side":"Sell","trade_id":"2"},
            {"ts":t,"price":101.0,"size":1,"side":"Buy","trade_id":"3"}]
    x=aggregate_minute("BTCUSDT",trades,.5)[0]
    assert x["delta"]==2 and x["poc_price"]==100.0 and x["trade_count"]==3


def test_live_footprint_deduplicates_trade_id():
    from grid.cluster import FootprintBuilder
    from grid.models import Trade
    fp=FootprintBuilder(.5,60)
    t=Trade("BTCUSDT",1767225600000,100.0,2.0,"Buy","same")
    assert fp.add(t) is True
    assert fp.add(t) is False
    row=fp.pop_closed(1767225660001)[0]
    assert row["trade_count"]==1
    assert row["buy_volume"]==2.0


def test_archive_stream_deduplicates_trade_id_and_rejects_time_reversal(tmp_path):
    import csv
    from grid.archive_stream_parser import iter_minute_aggregates
    p=tmp_path/"x.csv"
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["timestamp","side","price","size","trade_id"]);w.writeheader()
        w.writerow({"timestamp":"1767225600","side":"Buy","price":"100","size":"2","trade_id":"a"})
        w.writerow({"timestamp":"1767225600","side":"Buy","price":"100","size":"2","trade_id":"a"})
    rows=list(iter_minute_aggregates(str(p),"BTCUSDT",.5))
    assert rows[0]["trade_count"]==1
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["timestamp","side","price","size","trade_id"]);w.writeheader()
        w.writerow({"timestamp":"1767225601","side":"Buy","price":"100","size":"1","trade_id":"a"})
        w.writerow({"timestamp":"1767225600","side":"Sell","price":"100","size":"1","trade_id":"b"})
    try:list(iter_minute_aggregates(str(p),"BTCUSDT",.5))
    except ValueError as e: assert "monotonically" in str(e)
    else: raise AssertionError("out-of-order archive accepted")
