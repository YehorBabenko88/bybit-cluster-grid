from datetime import datetime,timedelta,timezone
from grid.ml_splits import walk_forward

def test_walk_forward_is_chronological_and_embargoed():
    a=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[{"event_ts":a+timedelta(hours=i)} for i in range(60)]
    folds=walk_forward(rows,folds=5,embargo_minutes=120)
    assert folds
    for train,valid in folds:
        assert max(x["event_ts"] for x in train) < min(x["event_ts"] for x in valid)-timedelta(minutes=120)

def test_walk_forward_never_randomly_mixes_future_into_train():
    a=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[{"event_ts":a+timedelta(minutes=i)} for i in range(100)]
    for train,valid in walk_forward(rows,folds=4,embargo_minutes=5):
        assert all(t["event_ts"]<valid[0]["event_ts"] for t in train)
