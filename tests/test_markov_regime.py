from datetime import datetime,timedelta,timezone
from grid.markov_regime import fit_fold_markov
def test_markov_is_fit_only_from_supplied_training_fold():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    train=[{"event_ts":t+timedelta(minutes=i),"market_state":s} for i,s in enumerate(["QUIET","HIGH_VOL","QUIET","HIGH_VOL"])]
    m=fit_fold_markov(train)
    p=m.probabilities("QUIET")
    assert p["HIGH_VOL"]>p["QUIET"]
    assert "IMPULSE" not in p
