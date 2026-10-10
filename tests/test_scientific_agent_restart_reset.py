import ast
from pathlib import Path


def test_scientific_start_rebuilds_volatile_agents_before_hydration():
    tree=ast.parse(Path("grid/scientific_service.py").read_text(encoding="utf-8"))
    start=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="start")
    lines={}
    for node in ast.walk(start):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=="orchestrator" for t in node.targets):
            lines["reset"]=node.lineno
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            if node.func.attr=="_hydrate_features":lines["features"]=node.lineno
            if node.func.attr=="_hydrate_micro_agents":lines["agents"]=node.lineno
    assert lines["reset"]<lines["features"]<lines["agents"]
