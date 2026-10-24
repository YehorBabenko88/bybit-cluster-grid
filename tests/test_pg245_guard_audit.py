"""Offline regression for independent PR245 password guard audit; no SQL or Docker."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_pg245_guard import inspect, main

GOOD = '''
async def create(admin, secret):
    if type(secret) is not str or len(secret) != 64 or any(ch not in '0123456789abcdef' for ch in secret):
        raise RuntimeError('PG18_INVALID_ROLE_SECRET_NO_MUTATIONS')
    await admin.execute(f'CREATE ROLE "{secret}"')
'''


class RoleSecretGuardAuditTests(unittest.TestCase):
    def test_valid_guard_shape(self):
        self.assertEqual(inspect(GOOD), "SOURCE_GUARD_SHAPE_PASS")

    def test_assert_guard_is_rejected(self):
        bad = GOOD.replace(
            "    if type(secret) is not str or len(secret) != 64 or any(ch not in '0123456789abcdef' for ch in secret):\n        raise RuntimeError('PG18_INVALID_ROLE_SECRET_NO_MUTATIONS')",
            "    assert len(secret) == 64\n    if False:\n        raise RuntimeError('PG18_INVALID_ROLE_SECRET_NO_MUTATIONS')")
        self.assertNotEqual(inspect(bad), "SOURCE_GUARD_SHAPE_PASS")

    def test_guard_after_sql_is_rejected(self):
        bad = GOOD.replace('    await admin.execute(f\'CREATE ROLE "{secret}"\')\n', '')
        bad = bad.replace('    if type(secret)', '    await admin.execute(f\'CREATE ROLE "{secret}"\')\n    if type(secret)')
        self.assertEqual(inspect(bad), "ROLE_SECRET_GUARD_ORDER")

    def test_optimized_interpreter_acceptance_and_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.py"
            path.write_text(GOOD, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(path)
            self.assertEqual(code, 0)
            receipt = json.loads(output.getvalue())
            self.assertEqual(receipt["status"], "SOURCE_GUARD_SHAPE_PASS")
            self.assertIs(receipt["sql_mutation_tested"], False)
            self.assertIs(receipt["physical_attestation"], False)


if __name__ == "__main__":
    unittest.main()
