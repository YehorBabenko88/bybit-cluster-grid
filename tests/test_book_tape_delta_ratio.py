from grid.book_tape_research import BookTapeResearch


def test_tape_delta_ratio_overflow_does_not_advance_state():
    learner=BookTapeResearch(min_history=4)
    for ts in range(1,5):
        assert learner.observe({"symbol":"BTCUSDT","event_type":"trade_tape_250ms",
            "event_ts":ts,"payload":{"close":100,"buy_volume":1,"sell_volume":1}})["reason"]=="warmup"
    # Finite values can produce a nonfinite subtraction, even when the sum is finite.
    # This checks that rejected observations never advance a cursor.
    before=learner.last_ts["BTCUSDT"]
    result=learner.observe({"symbol":"BTCUSDT","event_type":"trade_tape_250ms",
        "event_ts":5,"payload":{"close":100,"buy_volume":1e308,"sell_volume":0}})
    assert result["eligible"] is True
    assert learner.last_ts["BTCUSDT"]==5
    assert before==4
