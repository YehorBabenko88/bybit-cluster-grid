import ast
from pathlib import Path


def test_failed_checkpoint_restores_durable_cursor_before_retry():
    tree=ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="run_once")
    guarded=[n for n in ast.walk(method) if isinstance(n,ast.Try)
             and any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)
                     and x.func.attr=="_checkpoint" for x in ast.walk(ast.Module(body=n.body,type_ignores=[])))]
    assert guarded
    handler=next(h for h in guarded[0].handlers if isinstance(h.type,ast.Name) and h.type.id=="BaseException")
    assert any(isinstance(n,ast.Attribute) and n.attr=="last_id" for n in ast.walk(handler))
    assert any(isinstance(n,ast.Attribute) and n.attr=="last_event_ts" for n in ast.walk(handler))
    assert any(isinstance(n,ast.Raise) for n in ast.walk(handler))
