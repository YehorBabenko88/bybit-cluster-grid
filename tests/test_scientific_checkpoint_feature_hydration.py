import ast
from pathlib import Path


def test_feature_hydration_is_bounded_by_durable_checkpoint():
    tree = ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    hydrate = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                   and n.name == "_hydrate_features")
    fetch = next(n for n in ast.walk(hydrate) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "fetch")
    sql = fetch.args[0].value
    assert "ts<=$1" in sql
    assert len(fetch.args) == 2
    assert isinstance(fetch.args[1], ast.Attribute)
    assert fetch.args[1].attr == "last_event_ts"
