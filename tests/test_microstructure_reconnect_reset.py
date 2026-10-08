"""WebSocket reconnect must not carry stale market state into a new feed epoch."""
from pathlib import Path


def test_microstructure_resets_state_before_each_connection():
    source=Path("grid/microstructure.py").read_text(encoding="utf-8")
    start=source.index("        while True:\n            # A new socket starts")
    end=source.index("                async with websockets.connect(",start)
    section=source[start:end]
    for statement in (
        "books.clear()",
        "tickers.clear()",
        "last_book_write.clear()",
        "last_ticker_write.clear()",
        "quality.clear()",
        "guards.clear()",
        "velocity=BookVelocity()",
        "wall_tracker=WallTracker()",
    ):
        assert statement in section
