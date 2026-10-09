from pathlib import Path


def test_dataset_requires_known_completed_target_horizon():
    source = Path("grid/ml_dataset_builder.py").read_text(encoding="utf-8")
    assert "label_end_ts IS NOT NULL" in source
    assert "label_end_ts<$1" in source
    assert "COALESCE(label_end_ts,event_ts)" not in source
