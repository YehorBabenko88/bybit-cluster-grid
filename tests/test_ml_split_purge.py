from datetime import datetime,timedelta,timezone
from grid.ml_splits import walk_forward
def test_walk_forward_purges_overlapping_labels_and_groups():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[]
    for i in range(18):
        rows.append({"event_ts":t+timedelta(hours=i),"label_end_ts":t+timedelta(hours=i,minutes=30),
                     "split_group":("shared" if i in (4,6) else f"g{i}")})
    folds=walk_forward(rows,folds=2,embargo_minutes=10)
    assert folds
    for train,valid in folds:
        boundary=valid[0]["event_ts"]-timedelta(minutes=10)
        vg={x["split_group"] for x in valid}
        assert all(x["label_end_ts"]<boundary for x in train)
        assert all(x["split_group"] not in vg for x in train)
