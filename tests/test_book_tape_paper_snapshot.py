import json
import pytest
from grid.book_tape_paper import BookTapePaperLearner


def event(ts,price):
    return {"symbol":"BTCUSDT","event_type":"trade_tape_250ms",
            "event_ts":ts,"payload":{"close":price,"buy_volume":10,"sell_volume":1}}


def test_checkpoint_roundtrip_preserves_warmup_and_timestamps():
    original=BookTapePaperLearner()
    for i in range(10):
        original.observe(event(1000+i*250,100+i*.01))
    state=json.loads(json.dumps(original.snapshot()))
    restored=BookTapePaperLearner()
    restored.restore(state)
    assert restored.snapshot()==state
    assert restored.observe(event(1000,200))["reason"]=="replayed_or_out_of_order"
    assert restored.observe(event(4000,101))["eligible"] is True


def test_checkpoint_preserves_pending_and_directional_stats():
    original=BookTapePaperLearner()
    original.pending["BTCUSDT"].append({"due_ms":2000,"entry_ts_ms":1000,
        "entry_price":100.0,"direction":1,"pattern":"jbe"})
    original.stats[("BTCUSDT","jbe",1)]={"count":3,"wins":2,"net_bps_sum":8.5}
    restored=BookTapePaperLearner()
    restored.restore(json.loads(json.dumps(original.snapshot())))
    assert restored.pending["BTCUSDT"][0]["entry_price"]==100
    assert restored.stats[("BTCUSDT","jbe",1)]["wins"]==2


def test_invalid_snapshot_does_not_mutate_existing_state():
    learner=BookTapePaperLearner()
    learner.observe(event(1000,100))
    before=learner.snapshot()
    bad=json.loads(json.dumps(before))
    bad["pending"]={"BTCUSDT":[{"due_ms":2000,"entry_ts_ms":1000,
        "entry_price":float("nan"),"direction":1,"pattern":"jbe"}]}
    with pytest.raises(ValueError):
        learner.restore(bad)
    assert learner.snapshot()==before


def test_incompatible_configuration_rejected():
    original=BookTapePaperLearner(cost_bps=4).snapshot()
    with pytest.raises(ValueError,match="configuration"):
        BookTapePaperLearner(cost_bps=5).restore(original)
