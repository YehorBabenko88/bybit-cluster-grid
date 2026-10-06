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


def test_remote_bundle_training_uses_walk_forward_not_in_sample_evaluation():
    from pathlib import Path
    text=Path("grid/ml_compute_entry.py").read_text(encoding="utf-8")
    section=text[text.index("async def train_bundle"):]
    assert "folds=walk_forward(rows)" in section
    assert "backend.predict(fold_model,valid)" in section
    assert "backend.evaluate(valid,pred" in section
    assert "backend.predict(model,rows)" not in section
    assert '"validation":"walk_forward"' in section
