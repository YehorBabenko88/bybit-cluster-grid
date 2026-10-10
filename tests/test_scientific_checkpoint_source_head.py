import ast
from pathlib import Path


def test_checkpoint_rejects_negative_cursor_without_assuming_retained_event_head():
    tree = ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    start = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "start")
    guards = [n for n in ast.walk(start) if isinstance(n, ast.If)
              and isinstance(n.test, ast.Compare)
              and any(isinstance(x, ast.Attribute) and x.attr == "last_id"
                      for x in ast.walk(n.test))]
    assert any(any(isinstance(x, ast.Raise) for x in ast.walk(g)) for g in guards)
    assert not any(isinstance(x, ast.Name) and x.id == "source_head"
                   for x in ast.walk(start))
