from datetime import datetime,timezone
from grid.book_tape_research import BookTapeResearch


def test_invalid_datetime_timestamp_does_not_mutate_tape():
    learner=BookTapeResearch()
    event={"symbol":"BTCUSDT","event_type":"trade_tape_250ms",
           "event_ts":datetime.max.replace(tzinfo=timezone.utc),
           "payload":{"close":100,"buy_volume":1,"sell_volume":1}}
    # A valid large datetime may be representable: the important invariant is
    # that an exception from timestamp conversion never escapes.
    class BrokenTimestamp:
        def timestamp(self):
            raise OverflowError("out of supported range")
    event["event_ts"]=BrokenTimestamp()
    result=learner.observe(event)
    assert result["reason"]=="invalid_trade_bucket"
    assert "BTCUSDT" not in learner.last_ts
