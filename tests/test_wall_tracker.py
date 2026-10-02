from grid.wall_tracker import WallTracker


def test_wall_tracker_measures_lifetime_and_replenishment():
    w=WallTracker()

    first,removed=w.update(
        "BTCUSDT",
        1000,
        [{"side":"bid","price":100.0,"qty":10.0,"ratio":5.0}],
    )
    second,removed2=w.update(
        "BTCUSDT",
        1250,
        [{"side":"bid","price":100.0,"qty":14.0,"ratio":6.0}],
    )

    assert removed==[]
    assert removed2==[]
    assert first[0]["lifetime_ms"]==0
    assert second[0]["lifetime_ms"]==250
    assert second[0]["replenished_qty"]==4.0
    assert second[0]["replenishment_ratio"]>0


def test_wall_tracker_emits_removed_wall_without_calling_it_execution():
    w=WallTracker()
    w.update(
        "BTCUSDT",
        1000,
        [{"side":"ask","price":101.0,"qty":20.0,"ratio":7.0}],
    )
    current,removed=w.update("BTCUSDT",1500,[])

    assert current==[]
    assert len(removed)==1
    assert removed[0]["side"]=="ask"
    assert removed[0]["price"]==101.0
    assert removed[0]["lifetime_ms"]==500
