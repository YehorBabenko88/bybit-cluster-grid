from pathlib import Path


def test_book_stall_watch_uses_monotonic_time_and_per_symbol_receipts():
    src=Path("grid/microstructure.py").read_text(encoding="utf-8")
    assert "last_book_seen={sym:asyncio.get_running_loop().time() for sym in symbols}" in src
    assert "now=asyncio.get_running_loop().time()" in src
    assert "now-seen>book_stall_seconds" in src
    assert "stalled orderbook topics:" in src
    assert "last_book_seen[sym]=now" in src


def test_short_idle_poll_does_not_force_reconnect():
    src=Path("grid/microstructure.py").read_text(encoding="utf-8")
    assert "except asyncio.TimeoutError:" in src
    assert "raw=None" in src
    assert "if raw is None:" in src
