"""Regression tests for physical G1 guard boundaries, no host or SQL mutations."""
import ast
import json
from pathlib import Path
from installer.ls5_network_offline import evaluate

def test_network_policy_rejects_oversize_and_bad_unicode():
    for raw in ('x' * 65537, '\ud800', '\udfff', b'{}', json.dumps({'x':'😀' * 16385}, ensure_ascii=False)):
        result = evaluate(raw)
        assert result['policy_valid'] is False
        assert result['execution_authorized'] is False
        assert result['physical_ready'] is False

def test_pg18_credential_validation_survives_optimized_python():
    source = (Path(__file__).resolve().parent / '_pg18_database.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    # Under -O, assert nodes disappear; a required security guard must be an explicit raise.
    guards = [n for n in ast.walk(tree) if isinstance(n, ast.Raise) and
              isinstance(n.exc, ast.Call) and
              isinstance(n.exc.func, ast.Name) and n.exc.func.id == 'RuntimeError' and
              n.exc.args and isinstance(n.exc.args[0], ast.Constant) and
              n.exc.args[0].value == 'PG18_INVALID_ROLE_SECRET_NO_MUTATIONS']
    assert guards
    assert 'assert len(secret)' not in source
