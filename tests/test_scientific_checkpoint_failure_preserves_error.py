import ast
from pathlib import Path


def test_checkpoint_failure_preserves_original_exception_without_db_retry():
    tree=ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    run=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="run_once")
    guarded=[n for n in ast.walk(run) if isinstance(n,ast.Try)
             and any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)
                     and x.func.attr=="_checkpoint" for x in n.body)]
    assert len(guarded)==1
    handler=next(h for h in guarded[0].handlers if isinstance(h.type,ast.Name) and h.type.id=="BaseException")
    assert len(handler.body)==2
    assert isinstance(handler.body[0],ast.Assign)
    assert isinstance(handler.body[0].targets[0],ast.Attribute)
    assert handler.body[0].targets[0].attr=="started"
    assert isinstance(handler.body[0].value,ast.Constant) and handler.body[0].value.value is False
    assert isinstance(handler.body[1],ast.Raise) and handler.body[1].exc is None
