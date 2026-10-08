from grid.wall_tracker import WallTracker


def test_duplicate_and_backward_timestamps_do_not_corrupt_wall_history():
    tracker=WallTracker()
    first=[{"side":"bid","price":100,"qty":10,"ratio":8}]
    out,removed=tracker.update("BTCUSDT",1000,first)
    assert len(out)==1 and not removed
    for ts in (1000,999):
        out,removed=tracker.update("BTCUSDT",ts,[{"side":"bid","price":100,"qty":99,"ratio":8}])
        assert out==[] and removed==[]
        assert tracker.state["BTCUSDT"][("bid",100.0)]["last_qty"]==10
    out,removed=tracker.update("BTCUSDT",2000,[{"side":"bid","price":100,"qty":12,"ratio":8}])
    assert not removed
    assert out[0]["lifetime_ms"]==1000
    assert out[0]["replenished_qty"]==2


def test_independent_symbols_are_not_blocked_by_other_symbol_timestamps():
    tracker=WallTracker()
    wall=[{"side":"bid","price":100,"qty":10,"ratio":8}]
    tracker.update("BTCUSDT",2000,wall)
    out,removed=tracker.update("ETHUSDT",1000,wall)
    assert len(out)==1 and not removed
