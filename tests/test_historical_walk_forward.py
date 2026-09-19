from datetime import datetime,timedelta,timezone
from grid.historical_variant_engine import chronological_folds
def test_walk_forward_validation_windows_do_not_overlap_training_future():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[{"event_ts":t+timedelta(minutes=i)} for i in range(150)]
    folds=chronological_folds(rows,min_train=90,folds=3)
    assert len(folds)==3
    for _,train,val in folds:
        assert max(x["event_ts"] for x in train)<min(x["event_ts"] for x in val)
