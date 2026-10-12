import ast
from pathlib import Path


def test_micro_signal_trade_reference_requires_nonnegative_age():
    tree = ast.parse(Path("grid/scientific_event_router.py").read_text(encoding="utf-8"))
    route = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                 and n.name == "route_market_event")
    age = next(n.value for n in ast.walk(route) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "fresh_ref" for t in n.targets))
    assert any(isinstance(n, ast.Compare) and len(n.ops) == 2
               and isinstance(n.ops[0], ast.LtE) and isinstance(n.ops[1], ast.LtE)
               and isinstance(n.comparators[1], ast.Constant)
               and n.comparators[1].value == 3000 for n in ast.walk(age))
