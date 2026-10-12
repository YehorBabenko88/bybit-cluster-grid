import ast
from pathlib import Path


def test_micro_agent_hydration_respects_checkpoint_timestamp():
    tree = ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "_hydrate_micro_agents")
    fetch = next(n for n in ast.walk(method) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "fetch")
    assert "event_ts<=$2" in fetch.args[0].value
    assert len(fetch.args) == 3
    assert isinstance(fetch.args[2], ast.Attribute)
    assert fetch.args[2].attr == "last_event_ts"
