import ast
from pathlib import Path


def test_mining_and_simulation_queue_have_separate_failure_boundaries():
    source = Path("grid/scientific_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "run")
    guarded = {}
    for handler in (n for n in ast.walk(run) if isinstance(n, ast.Try)):
        names = {
            node.func.attr for statement in handler.body for node in ast.walk(statement)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        for target in ("run_closed_split_once", "run_queued"):
            if target in names:
                guarded[target] = handler
    assert set(guarded) == {"run_closed_split_once", "run_queued"}
    assert guarded["run_closed_split_once"] is not guarded["run_queued"]
    for handler in guarded.values():
        assert any(any(isinstance(node, ast.Name) and node.id == "CancelledError"
                       for node in ast.walk(h.type)) for h in handler.handlers if h.type)
        assert any(any(isinstance(node, ast.Name) and node.id == "Exception"
                       for node in ast.walk(h.type)) for h in handler.handlers if h.type)
