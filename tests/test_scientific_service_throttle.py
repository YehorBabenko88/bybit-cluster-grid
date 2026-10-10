import ast
from pathlib import Path


def test_scientific_service_throttles_background_simulations():
    source = Path("grid/scientific_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "run")
    checks = [n for n in ast.walk(run) if isinstance(n, ast.If)
              and isinstance(n.test, ast.Compare)
              and any(isinstance(c, ast.Constant) and c.value == 30 for c in ast.walk(n.test))]
    assert len(checks) == 1
    queue_calls = [n for n in ast.walk(run) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr == "run_queued"]
    assert len(queue_calls) == 1
    assert queue_calls[0].lineno in range(checks[0].lineno, checks[0].end_lineno + 1)
    assert any(k.arg == "limit" and isinstance(k.value, ast.Constant) and k.value.value == 1
               for k in queue_calls[0].keywords)
