from pathlib import Path


def test_ticker_deltas_are_filtered_before_merging():
    source=Path("grid/microstructure.py").read_text(encoding="utf-8")
    start=source.index('                        if topic.startswith("tickers."):')
    end=source.index('                            state.update(',start)
    section=source[start:end]
    assert 'if ts<last_ticker_seen.get(sym,-1):' in section
    assert 'last_ticker_seen[sym]=ts' in section
    assert section.index('if ts<last_ticker_seen') < section.index('state=tickers.setdefault')


def test_ticker_timestamp_guard_resets_after_reconnect():
    source=Path("grid/microstructure.py").read_text(encoding="utf-8")
    assert "last_ticker_seen={}" in source
    assert "last_ticker_seen.clear()" in source
