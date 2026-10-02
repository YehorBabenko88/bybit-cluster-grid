from grid.cluster import FootprintBuilder
from grid.models import Trade


def trade(ts_ms, price=100.0, qty=1.0, side="Buy"):
    return Trade("BTCUSDT", ts_ms, price, qty, side, str(ts_ms))


def test_builder_waits_for_finalization_delay():
    fp=FootprintBuilder(0.1, interval_s=60, finalization_delay_ms=2000)
    assert fp.add(trade(1_000))
    assert fp.pop_closed(60_000) == []
    assert fp.pop_closed(61_999) == []
    rows=fp.pop_closed(62_000)
    assert len(rows) == 1
    assert rows[0]["start_ms"] == 0
    assert rows[0]["trade_count"] == 1


def test_late_trade_cannot_reopen_finalized_minute():
    fp=FootprintBuilder(0.1, interval_s=60, finalization_delay_ms=2000)
    assert fp.add(trade(1_000))
    rows=fp.pop_closed(62_000)
    assert len(rows) == 1
    assert fp.add(trade(59_999, price=101.0)) is False
    assert fp.pop_closed(120_000) == []


def test_trade_inside_grace_is_merged_before_finalization():
    fp=FootprintBuilder(0.1, interval_s=60, finalization_delay_ms=2000)
    assert fp.add(trade(1_000, price=100.0))
    assert fp.pop_closed(60_500) == []
    assert fp.add(trade(59_900, price=101.0, qty=2.0))
    rows=fp.pop_closed(62_000)
    assert len(rows) == 1
    assert rows[0]["trade_count"] == 2
    assert rows[0]["open"] == 100.0
    assert rows[0]["close"] == 101.0
    assert rows[0]["high"] == 101.0
    assert rows[0]["buy_volume"] == 3.0


def test_finalization_watermark_is_per_symbol():
    fp=FootprintBuilder(0.1, interval_s=60, finalization_delay_ms=0)
    assert fp.add(trade(1_000))
    assert len(fp.pop_closed(60_000)) == 1
    eth=Trade("ETHUSDT", 1_000, 200.0, 1.0, "Buy", "eth")
    assert fp.add(eth) is True
