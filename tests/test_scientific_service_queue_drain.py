import ast
from pathlib import Path


def test_simulation_queue_drain_is_outside_hourly_mining_guard():
    tree = ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "run")
    mining = next(n for n in ast.walk(run) if isinstance(n, ast.If)
                  and isinstance(n.test, ast.Compare)
                  and any(isinstance(c, ast.Constant) and c.value == 3600 for c in ast.walk(n.test)))
    drains = [n for n in ast.walk(run) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr == "run_queued"]
    assert len(drains) == 1
    assert drains[0].lineno > mining.end_lineno
