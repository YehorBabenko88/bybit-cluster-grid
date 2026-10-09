import pytest
from grid.book_tape_paper import BookTapePaperLearner


class FixedSignal:
    def observe(self,event):
        return {"eligible":True,"ts_ms":event["event_ts"],"direction":1,
                "decision":"PAPER_CANDIDATE",
                "patterns":{"jbe_proxy":True,"dbi_proxy":False}}


def event(ts,price):
    return {"symbol":"BTCUSDT","event_ts":ts,
            "payload":{"close":price}}


def test_stale_exit_does_not_train_or_count_as_profit():
    learner=BookTapePaperLearner(horizon_ms=1000,max_exit_delay_ms=100)
    learner.signal=FixedSignal()
    learner.observe(event(1000,100))
    result=learner.observe(event(10000,200))
    assert result["paper"]["matured"]==[]
    assert len(result["paper"]["expired"])==1
    assert result["paper"]["expired"][0]["reason"]=="stale_exit_price"
    assert result["paper"]["historical_count"]==0
    assert learner.stats[("BTCUSDT","jbe",1)]["count"]==0


def test_on_time_exit_still_trains():
    learner=BookTapePaperLearner(horizon_ms=1000,max_exit_delay_ms=100)
    learner.signal=FixedSignal()
    learner.observe(event(1000,100))
    result=learner.observe(event(2050,101))
    assert len(result["paper"]["matured"])==1
    assert result["paper"]["expired"]==[]
    assert result["paper"]["historical_count"]==1


@pytest.mark.parametrize("invalid",[-1,1.5,True])
def test_invalid_exit_delay_rejected(invalid):
    with pytest.raises(ValueError):
        BookTapePaperLearner(max_exit_delay_ms=invalid)
