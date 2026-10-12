from grid.book_tape_research import BookTapeResearch


def _event(ts,buy,sell):
    return {"symbol":"BTCUSDT","event_type":"trade_tape_250ms","event_ts":ts,
            "payload":{"close":100.0,"buy_volume":buy,"sell_volume":sell}}


def test_overflowed_tape_volume_does_not_advance_history():
    learner=BookTapeResearch(min_history=4)
    invalid=learner.observe(_event(1,1e308,1e308))
    assert invalid["reason"]=="invalid_trade_bucket"
    assert "BTCUSDT" not in learner.last_ts
    assert not learner.history["BTCUSDT"]
    assert learner.observe(_event(1,1,1))["reason"]=="warmup"


def test_overflowed_relative_volume_does_not_advance_history():
    learner=BookTapeResearch(min_history=4)
    for ts in range(1,5):
        assert learner.observe(_event(ts,1e-300,1e-300))["reason"]=="warmup"
    invalid=learner.observe(_event(5,1e308,0))
    assert invalid["reason"]=="invalid_relative_volume"
    assert learner.last_ts["BTCUSDT"]==4
    assert len(learner.history["BTCUSDT"])==4
