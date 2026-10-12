import ast
from pathlib import Path


def test_all_waiting_calls_include_attempt_token():
    tree = ast.parse(Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("_waiting", "_fail")
    ]
    assert len(calls) >= 4
    for call in calls:
        assert len(call.args) == 3, f"{call.func.attr} at line {call.lineno} must receive run_id, attempt_id, reason"
        assert isinstance(call.args[1], ast.Name)
        assert call.args[1].id == "attempt_id"
