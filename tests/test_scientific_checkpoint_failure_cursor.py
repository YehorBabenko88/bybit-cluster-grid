import ast
from pathlib import Path


def test_failed_checkpoint_forces_reload_of_durable_cursor_on_next_start():
    tree=ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    service=next(n for n in tree.body if isinstance(n,ast.ClassDef)
                 and n.name=="ScientificResearchService")
    run=next(n for n in service.body if isinstance(n,ast.AsyncFunctionDef)
             and n.name=="run_once")
    start=next(n for n in service.body if isinstance(n,ast.AsyncFunctionDef)
               and n.name=="start")
    assert any(isinstance(n,ast.If) and any(isinstance(x,ast.Call)
               and isinstance(x.func,ast.Attribute) and x.func.attr=="start"
               for x in ast.walk(n)) for n in run.body)
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
               and n.func.attr=="fetchrow" for n in ast.walk(start))
    assert any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute)
               and t.attr=="last_id" for t in n.targets) for n in ast.walk(start))
