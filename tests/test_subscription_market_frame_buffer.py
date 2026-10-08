from pathlib import Path


def test_subscription_frames_buffered_before_ack():
    source = (Path(__file__).resolve().parents[1] / "grid" / "microstructure.py").read_text()
    assert "pending_market_frames=[]" in source
    assert 'ack["topic"].startswith(("orderbook.","tickers."))' in source
    assert "pending_market_frames.append(raw)" in source
    assert "raw=pending_market_frames.pop(0)" in source
    assert 'subscription market frame buffer overflow' in source
