import ast
from pathlib import Path


def test_scientific_restart_rebinds_builtin_learner_without_discarding_registry():
    tree=ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    service=next(n for n in tree.body if isinstance(n,ast.ClassDef)
                 and n.name=="ScientificResearchService")
    start=next(n for n in service.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="start")
    resets=[n for n in ast.walk(start) if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Attribute) and t.attr=="book_tape" for t in n.targets)
            and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name)
            and n.value.func.id=="BookTapePaperLearner"]
    assert len(resets)==1
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
               and n.func.id=="replace" for n in ast.walk(start))
    assert not any(isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Attribute) and t.attr=="methods" for t in n.targets)
                   for n in ast.walk(start))
