from pathlib import Path


def test_evaluation_ordering_is_deterministic():
    source = Path("grid/ml_evaluation_pipeline.py").read_text(encoding="utf-8")
    assert "ORDER BY e.created_at DESC,e.id DESC LIMIT 1" in source
    assert "ORDER BY created_at DESC,id DESC LIMIT 1" in source
    assert "ORDER BY created_at DESC,id DESC" in source
    assert "ORDER BY created_at DESC LIMIT 1" not in source
