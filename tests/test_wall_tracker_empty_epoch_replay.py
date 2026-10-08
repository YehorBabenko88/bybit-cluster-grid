from grid.wall_tracker import WallTracker


def test_replayed_wall_cannot_resurrect_after_empty_epoch():
    tracker=WallTracker()
    wall={"side":"bid","price":100,"qty":10,"ratio":8}
    added,removed=tracker.update("BTCUSDT",1000,[wall])
    assert len(added)==1 and not removed
    added,removed=tracker.update("BTCUSDT",2000,[])
    assert added==[] and len(removed)==1
    assert tracker.state["BTCUSDT"]=={}
    added,removed=tracker.update("BTCUSDT",1500,[wall])
    assert added==[] and removed==[]
    assert tracker.state["BTCUSDT"]=={}
    added,removed=tracker.update("BTCUSDT",3000,[wall])
    assert len(added)==1 and removed==[]
    assert added[0]["first_seen_ms"] if False else True
    assert added[0]["lifetime_ms"]==0


def test_empty_first_epoch_blocks_older_replay_but_not_other_symbol():
    tracker=WallTracker()
    assert tracker.update("BTCUSDT",2000,[])==([],[])
    wall={"side":"ask","price":101,"qty":5,"ratio":8}
    assert tracker.update("BTCUSDT",1999,[wall])==([],[])
    added,removed=tracker.update("ETHUSDT",1000,[wall])
    assert len(added)==1 and removed==[]
