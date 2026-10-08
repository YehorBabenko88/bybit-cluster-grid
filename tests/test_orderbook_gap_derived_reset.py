"""Derived orderbook metrics must not span an invalid sequence epoch."""
from pathlib import Path


def test_book_gap_invalidates_velocity_and_wall_baselines():
    source=Path("grid/microstructure.py").read_text(encoding="utf-8")
    start=source.index("                            elif not guard.delta(")
    end=source.index("                                continue",start)
    section=source[start:end]
    assert "velocity.state.pop(sym,None)" in section
    assert "wall_tracker.state.pop(sym,None)" in section
    assert 'q.mark("orderbook",MISSING' in section


def test_new_snapshot_after_invalid_guard_resets_derived_baselines():
    source=Path("grid/microstructure.py").read_text(encoding="utf-8")
    start=source.index("                            if is_snapshot:")
    end=source.index('                                state["b"]=',start)
    section=source[start:end]
    assert "if not guard.valid:" in section
    assert "velocity.state.pop(sym,None)" in section
    assert "wall_tracker.state.pop(sym,None)" in section
