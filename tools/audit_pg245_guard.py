"""Independent read-only PR245 role-secret guard auditor.

Usage: python tools/audit_pg245_guard.py /path/to/tests/_pg18_database.py
Requires exact checked-out source supplied by reviewer. Never connects to PostgreSQL.
"""
import ast
import json
import pathlib
import subprocess
import sys

def inspect(source):
    tree = ast.parse(source)
    if any(isinstance(node, ast.Assert) for node in ast.walk(tree)):
        return "ASSERT_IN_FIXTURE"
    lines = source.splitlines()
    guards = [i for i, line in enumerate(lines) if "PG18_INVALID_ROLE_SECRET_NO_MUTATIONS" in line]
    creates = [i for i, line in enumerate(lines) if "CREATE ROLE" in line and "await admin.execute" in line]
    if len(guards) != 1 or len(creates) != 1 or guards[0] >= creates[0]:
        return "ROLE_SECRET_GUARD_ORDER"
    guard = lines[guards[0]]
    if "raise RuntimeError" not in guard:
        return "NOT_UNCONDITIONAL_EXCEPTION"
    if not any("type(secret) is not str" in line for line in lines[max(0, guards[0]-4):guards[0]+1]):
        return "MISSING_SECRET_TYPE_CHECK"
    if not any("len(secret) != 64" in line for line in lines[max(0, guards[0]-4):guards[0]+1]):
        return "MISSING_SECRET_LENGTH_CHECK"
    if not any("0123456789abcdef" in line for line in lines[max(0, guards[0]-4):guards[0]+1]):
        return "MISSING_SECRET_ALPHABET_CHECK"
    return "SOURCE_GUARD_SHAPE_PASS"

def main(path):
    source = pathlib.Path(path).read_text(encoding="utf-8")
    result = inspect(source)
    # Execute the actual guard expression from the source under optimized Python.
    if result == "SOURCE_GUARD_SHAPE_PASS":
        tree = ast.parse(source)
        guard_if = next((n for n in ast.walk(tree) if isinstance(n, ast.If)
                         and any(isinstance(x, ast.Raise) and isinstance(x.exc, ast.Call)
                                 and isinstance(x.exc.func, ast.Name)
                                 and x.exc.func.id == "RuntimeError"
                                 and x.exc.args and isinstance(x.exc.args[0], ast.Constant)
                                 and x.exc.args[0].value == "PG18_INVALID_ROLE_SECRET_NO_MUTATIONS"
                                 for x in n.body)), None)
        if guard_if is None:
            result = "GUARD_AST_NOT_FOUND"
        else:
            expression = ast.unparse(guard_if.test)
            script = ("import sys\nsecret=sys.argv[1]\n"
                      "if " + expression + ": raise RuntimeError('PG18_INVALID_ROLE_SECRET_NO_MUTATIONS')\n"
                      "print('ACCEPTED')\n")
            cases = [("a"*64, True), ("a"*63, False), ("A"*64, False),
                     ("g"*64, False), ("'"*64, False)]
            for secret, allowed in cases:
                proc = subprocess.run([sys.executable, "-O", "-c", script, secret],
                                      capture_output=True, text=True, timeout=10)
                if (proc.returncode == 0) != allowed:
                    result = "OPTIMIZED_GUARD_BYPASS"
                    break
    print(json.dumps({"status": result, "physical_attestation": False,
                      "sql_mutation_tested": False}, sort_keys=True))
    return 0 if result == "SOURCE_GUARD_SHAPE_PASS" else 2

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
