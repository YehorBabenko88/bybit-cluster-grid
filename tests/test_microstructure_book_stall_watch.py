from grid.topic_watchdog import TopicWatchdog
from pathlib import Path


def test_stall_one_symbol_while_another_continues():
    w=TopicWatchdog(["BTCUSDT","ETHUSDT"],started_at=0,timeout_seconds=120)
    w.observe("BTCUSDT",119)
    assert w.stalled(120)==[]
    assert w.stalled(121)==["ETHUSDT"]
    w.observe("ETHUSDT",122)
    assert w.stalled(122)==[]
    assert w.stalled(240)==["BTCUSDT"]


def test_reconnect_creates_fresh_watchdog_epoch():
    old=TopicWatchdog(["BTCUSDT"],started_at=0)
    assert old.stalled(121)==["BTCUSDT"]
    fresh=TopicWatchdog(["BTCUSDT"],started_at=121)
    assert fresh.stalled(121)==[]
    assert fresh.stalled(242)==["BTCUSDT"]


def test_unknown_topic_does_not_expand_watchdog():
    w=TopicWatchdog(["BTCUSDT"],started_at=0)
    w.observe("UNSUBSCRIBED",100)
    assert list(w.last_seen)==["BTCUSDT"]


def test_collector_wires_monotonic_watchdog_and_idle_poll():
    src=Path("grid/microstructure.py").read_text(encoding="utf-8")
    assert "TopicWatchdog(symbols,asyncio.get_running_loop().time()" in src
    assert "book_watchdog.stalled(now)" in src
    assert "book_watchdog.observe(sym,now)" in src
    assert "except asyncio.TimeoutError:" in src
    assert "if raw is None:" in src
