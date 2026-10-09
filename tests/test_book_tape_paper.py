from grid.book_tape_paper import BookTapePaperLearner


class FixedSignal:
    def __init__(self):
        self.last=-1

    def observe(self,event):
        ts=event["event_ts"]
        if ts<=self.last:
            return {"eligible":False,"reason":"replayed_or_out_of_order"}
        self.last=ts
        return {"eligible":True,"ts_ms":ts,"direction":1,"decision":"PAPER_CANDIDATE",
                "patterns":{"jbe_proxy":True,"dbi_proxy":False}}


def event(ts,price):
    return {"symbol":"BTCUSDT","event_type":"trade_tape_250ms",
            "event_ts":ts,"payload":{"close":price}}


def test_delayed_paper_labels_use_only_future_events():
    learner=BookTapePaperLearner(horizon_ms=1000,cost_bps=2,min_samples=2)
    learner.signal=FixedSignal()
    first=learner.observe(event(1000,100))
    assert first["paper"]["historical_count"]==0
    second=learner.observe(event(1500,101))
    assert second["paper"]["matured"]==[]
    third=learner.observe(event(2000,99))
    assert third["paper"]["historical_count"]==1
    assert third["paper"]["matured"][0]["net_bps"]<0
    assert third["paper"]["matured"][0]["entry_ts_ms"]==1000


def test_negative_matured_evidence_blocks_new_candidates():
    learner=BookTapePaperLearner(horizon_ms=1000,cost_bps=2,min_samples=1)
    learner.signal=FixedSignal()
    learner.observe(event(1000,100))
    result=learner.observe(event(2000,99))
    assert result["decision"]=="ABSTAIN_NEGATIVE_PAPER_EVIDENCE"
    assert result["direction"]==0
    assert result["paper"]["historical_count"]==1
    assert result["paper"]["pending"]==0


def test_pending_capacity_fail_closed_and_symbol_local():
    learner=BookTapePaperLearner(horizon_ms=10000,max_pending=1)
    learner.signal=FixedSignal()
    learner.observe(event(1000,100))
    result=learner.observe(event(2000,101))
    assert result["decision"]=="ABSTAIN_PAPER_BACKLOG"
    assert result["paper"]["pending"]==1
