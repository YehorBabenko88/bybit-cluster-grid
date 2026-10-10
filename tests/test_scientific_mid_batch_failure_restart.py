import ast
from pathlib import Path


def test_scientific_mid_batch_failure_invalidates_volatile_state():
    tree=ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    run=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="run_once")
    guarded=[n for n in ast.walk(run) if isinstance(n,ast.Try)
             and any(isinstance(x,ast.For) for x in n.body)]
    assert guarded
    handler=next(h for h in guarded[0].handlers
                 if isinstance(h.type,ast.Name) and h.type.id=="BaseException")
    assert any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute)
               and t.attr=="started" for t in n.targets)
               and isinstance(n.value,ast.Constant) and n.value.value is False
               for n in handler.body)
    assert isinstance(handler.body[-1],ast.Raise)
