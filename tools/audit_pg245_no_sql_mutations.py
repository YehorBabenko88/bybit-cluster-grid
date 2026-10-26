"""Execute the real PR245 database fixture under python -O with a SQL recorder.

No PostgreSQL connection, no Docker, no mutations. Supply an exact checked-out
tests/_pg18_database.py from PR245. Fake modules are injected before import.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

EXPECTED_ERROR = "PG18_INVALID_ROLE_SECRET_NO_MUTATIONS"
MUTATION = re.compile(r"^\s*(CREATE|ALTER|DROP|GRANT|REVOKE|INSERT|UPDATE|DELETE|TRUNCATE)\b", re.I)


def run_case(path, secret):
    import os
    import types
    calls = []
    identity = "1234567890123"
    class Admin:
        async def fetchval(self, sql):
            calls.append(("fetchval", sql))
            if "system_identifier" in sql:
                return identity
            if "server_version_num" in sql:
                return "180004"
            raise RuntimeError("UNEXPECTED_QUERY")
        async def execute(self, sql):
            calls.append(("execute", sql))
            if sql.strip() != "SET default_transaction_read_only=off":
                raise RuntimeError("UNEXPECTED_SQL_EXECUTION")
        async def close(self):
            calls.append(("close", ""))
        def is_closed(self):
            return False
    admin = Admin()
    async def connect(**kwargs):
        calls.append(("connect", dict(kwargs)))
        return admin
    asyncpg = types.ModuleType("asyncpg")
    asyncpg.connect = connect
    ci = types.ModuleType("tools.ci_pg18")
    ci.attest = lambda: identity
    grid = types.ModuleType("grid")
    grid.__path__ = []
    db = types.ModuleType("grid.db")
    db.configure_connection = lambda _: None
    sys.modules.update({"asyncpg": asyncpg, "tools.ci_pg18": ci, "grid": grid, "grid.db": db})
    os.environ["GRID_PG18_PORT"] = "49100"
    os.environ["GRID_PG18_PASSWORD"] = secret
    spec = importlib.util.spec_from_file_location("isolated_pg245_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async def exercise():
        try:
            async with module.database(prepared=False):
                raise RuntimeError("UNEXPECTED_CONTEXT_ENTER")
        except RuntimeError as exc:
            if str(exc) != EXPECTED_ERROR:
                raise
    asyncio.run(exercise())
    execute_calls = [sql for action, sql in calls if action == "execute"]
    if execute_calls != ["SET default_transaction_read_only=off"]:
        raise RuntimeError("UNEXPECTED_SQL_EXECUTION_SEQUENCE")
    if not any(action == "connect" for action, _ in calls):
        raise RuntimeError("FIXTURE_NOT_EXERCISED")
    return {"status": "BLOCKED_INVALID_SECRET", "mutating_sql_calls": 0,
            "sql_execute_calls": len(execute_calls), "simulated_connection": True,
            "physical": "0/10 NOT_RUN", "real_postgres": False}


def main(path):
    cases = ["a" * 63, "A" * 64, "g" * 64, "'" * 64]
    for secret in cases:
        proc = subprocess.run([sys.executable, "-O", __file__, "--child", str(path), secret],
                              capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            raise RuntimeError("OPTIMIZED_FIXTURE_GUARD_FAILURE")
        result = json.loads(proc.stdout)
        if (result["mutating_sql_calls"] != 0 or result["status"] != "BLOCKED_INVALID_SECRET"
                or result["sql_execute_calls"] != 1 or result["real_postgres"] is not False):
            raise RuntimeError("INVALID_GUARD_RECEIPT")
    print(json.dumps({"cases": len(cases), "status": "OFFLINE_NEGATIVE_PASS",
                      "real_postgres": False, "physical_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        print(json.dumps(run_case(Path(sys.argv[2]), sys.argv[3]), sort_keys=True))
    elif len(sys.argv) == 2:
        main(Path(sys.argv[1]))
    else:
        raise SystemExit(2)
