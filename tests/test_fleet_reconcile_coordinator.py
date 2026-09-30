import ast
from pathlib import Path


COORDINATOR = Path(__file__).resolve().parents[1] / "grid" / "coordinator.py"


def _tree():
    return ast.parse(
        COORDINATOR.read_text(encoding="utf-8"),
        filename=str(COORDINATOR),
    )


def _async_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"async function {name!r} not found")


def _awaited_call_name(stmt):
    if not isinstance(stmt, ast.Expr):
        return None

    value = stmt.value
    if not isinstance(value, ast.Await):
        return None

    call = value.value
    if not isinstance(call, ast.Call):
        return None

    fn = call.func

    if isinstance(fn, ast.Name):
        return fn.id

    if isinstance(fn, ast.Attribute):
        return fn.attr

    return None


def test_command_result_reconciles_fleet_after_persisting_ack():
    tree = _tree()
    fn = _async_function(tree, "post_command_result")

    calls = [
        name
        for stmt in fn.body
        if (name := _awaited_call_name(stmt)) is not None
    ]

    assert "command_result" in calls
    assert "reconcile_fleet_operation" in calls

    assert calls.index("command_result") < calls.index(
        "reconcile_fleet_operation"
    )


def test_recovery_loop_reconciles_before_runtime_gate_check():
    tree = _tree()
    startup = _async_function(tree, "startup")

    loop_fn = None

    for stmt in startup.body:
        if isinstance(stmt, ast.AsyncFunctionDef) and stmt.name == "loop":
            loop_fn = stmt
            break

    assert loop_fn is not None, "startup.loop not found"

    while_node = next(
        (
            stmt
            for stmt in loop_fn.body
            if isinstance(stmt, ast.While)
        ),
        None,
    )

    assert while_node is not None, "coordinator loop while not found"

    try_node = next(
        (
            stmt
            for stmt in while_node.body
            if isinstance(stmt, ast.Try)
        ),
        None,
    )

    assert try_node is not None, "coordinator loop try block not found"

    reconcile_index = None
    gate_index = None

    for i, stmt in enumerate(try_node.body):
        if _awaited_call_name(stmt) == "reconcile_fleet_operation":
            reconcile_index = i

        if isinstance(stmt, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "gate"
                for target in stmt.targets
            ):
                value = stmt.value
                if (
                    isinstance(value, ast.Await)
                    and isinstance(value.value, ast.Call)
                    and isinstance(value.value.func, ast.Name)
                    and value.value.func.id == "runtime_state"
                ):
                    gate_index = i

    assert reconcile_index is not None, (
        "recovery reconcile_fleet_operation call missing"
    )

    assert gate_index is not None, (
        "runtime_state gate read missing"
    )

    assert reconcile_index < gate_index, (
        "fleet reconcile must run before runtime gate check "
        "so STOPPING/RESUMING can recover after restart"
    )
