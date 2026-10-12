from grid.book_tape_paper import BookTapePaperLearner


def test_paper_return_accumulator_overflow_does_not_change_stats():
    learner=BookTapePaperLearner(horizon_ms=1)
    key=("BTCUSDT","trend",1)
    learner.stats[key]={"count":1,"wins":1,"net_bps_sum":1.79e308}
    learner.pending["BTCUSDT"].append({
        "due_ms":2,"entry_ts_ms":1,"entry_price":1.0,
        "direction":1,"pattern":"trend"})
    learner.signal.observe=lambda event:{
        "eligible":True,"ts_ms":2,"direction":0,
        "patterns":{"jbe_proxy":False,"dbi_proxy":False}}
    result=learner.observe({"symbol":"BTCUSDT","payload":{"close":1e304}})
    assert result["paper"]["expired"][0]["reason"]=="paper_return_accumulator_overflow"
    assert learner.stats[key]=={"count":1,"wins":1,"net_bps_sum":1.79e308}
