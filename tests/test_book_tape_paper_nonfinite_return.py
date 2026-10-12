from grid.book_tape_paper import BookTapePaperLearner


def test_nonfinite_paper_return_expires_without_polluting_stats():
    learner=BookTapePaperLearner(horizon_ms=1)
    learner.pending["BTCUSDT"].append({
        "due_ms":2,"entry_ts_ms":1,"entry_price":1e-300,
        "direction":1,"pattern":"trend"})
    learner.signal.observe=lambda event:{
        "eligible":True,"ts_ms":2,"direction":0,
        "patterns":{"jbe_proxy":False,"dbi_proxy":False}}
    result=learner.observe({"symbol":"BTCUSDT","payload":{"close":1e300}})
    assert result["paper"]["expired"][0]["reason"]=="invalid_paper_return"
    assert result["paper"]["matured"]==[]
    assert learner.stats[("BTCUSDT","trend",1)]["count"]==0
    assert not learner.pending["BTCUSDT"]
