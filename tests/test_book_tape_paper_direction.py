from grid.book_tape_paper import BookTapePaperLearner


class AlternatingSignals:
    def observe(self,event):
        return {"eligible":True,"ts_ms":event["event_ts"],
                "direction":event["direction"],"decision":"PAPER_CANDIDATE",
                "patterns":{"jbe_proxy":True,"dbi_proxy":False}}


def test_long_losses_do_not_block_short_signals():
    learner=BookTapePaperLearner(horizon_ms=1000,min_samples=1)
    learner.signal=AlternatingSignals()
    learner.observe({"symbol":"BTCUSDT","event_ts":1000,"direction":1,"payload":{"close":100}})
    short=learner.observe({"symbol":"BTCUSDT","event_ts":2000,"direction":-1,"payload":{"close":99}})
    assert short["direction"]==-1
    assert short["decision"]=="PAPER_CANDIDATE"
    assert learner.stats[("BTCUSDT","jbe",1)]["count"]==1
    assert learner.stats[("BTCUSDT","jbe",-1)]["count"]==0


def test_nonfinite_paper_configuration_rejected():
    for kw in ({"cost_bps":float("nan")},{"min_hit_rate":float("inf")},{"horizon_ms":0}):
        try:
            BookTapePaperLearner(**kw)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid config accepted: {kw}")
