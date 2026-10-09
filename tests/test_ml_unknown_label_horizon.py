from datetime import datetime, timedelta, timezone
from grid.ml_splits import walk_forward


def test_missing_label_end_is_not_used_for_training():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {"event_ts": t + timedelta(hours=i), "label_end_ts": None if i == 0 else t + timedelta(hours=i, minutes=5)}
        for i in range(12)
    ]
    folds = walk_forward(rows, folds=3, embargo_minutes=0)
    assert folds
    assert all(row["label_end_ts"] is not None for train, _ in folds for row in train)


def test_invalid_split_configuration_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        walk_forward([], folds=0)
    with pytest.raises(ValueError):
        walk_forward([], embargo_minutes=-1)
