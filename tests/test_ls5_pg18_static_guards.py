"""Offline fail-closed guard regression: no PostgreSQL or Docker connection."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = (
    ROOT / "tests" / "test_ls5_pg18_disposable.py",
    ROOT / "tests" / "test_ls5_pg18_restore.py",
)


class Pg18StaticGuardTests(unittest.TestCase):
    def test_no_optimization_removable_asserts(self):
        for source in SOURCES:
            with self.subTest(source=source.name):
                tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
                self.assertFalse(
                    [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)],
                    "Python -O strips assert, including destructive-action guards",
                )

    def test_restore_cleanup_is_owned(self):
        source = SOURCES[1].read_text(encoding="utf-8")
        self.assertIn("target = TARGET_PREFIX + uuid.uuid4().hex", source)
        self.assertIn("created_target = True", source)
        self.assertIn("if created_target:", source)
        self.assertNotIn('"--if-exists"', source)

    def test_restore_subprocess_guard_and_timeout(self):
        source = SOURCES[1].read_text(encoding="utf-8")
        self.assertIn("PG18_RESTORE_SUBPROCESS_GUARD", source)
        self.assertIn('timeout=90', source)
        self.assertIn('"RUNNER_ENVIRONMENT"', source)
        self.assertIn('"GITHUB_REPOSITORY"', source)


if __name__ == "__main__":
    unittest.main()
