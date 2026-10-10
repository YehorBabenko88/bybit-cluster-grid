import ast
from pathlib import Path


def test_scientific_checkpoint_cannot_resume_beyond_source_head():
    tree = ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    start = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "start")
    guards = [n for n in ast.walk(start) if isinstance(n, ast.If)
              and isinstance(n.test, ast.Compare)
              and any(isinstance(x, ast.Attribute) and x.attr == "last_id"
                      for x in ast.walk(n.test))
              and any(isinstance(x, ast.Name) and x.id == "source_head"
                      for x in ast.walk(n.test))]
    assert len(guards) == 1
    assert any(isinstance(n, ast.Raise) for n in ast.walk(guards[0]))
