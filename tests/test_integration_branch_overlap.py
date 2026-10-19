import unittest
from audit.integration_ci.branch_overlap import audit, collisions

class BranchOverlapTests(unittest.TestCase):
    def test_independent_paths(self):
        self.assertEqual(collisions({"a": ["tests/a.py"], "b": ["tests/b.py"]}), {})
    def test_collision(self):
        self.assertEqual(collisions({"a": ["same.py"], "b": ["same.py"]}), {"same.py": ["a", "b"]})
        self.assertEqual(audit({"a": ["same.py"], "b": ["same.py"]})["status"], "BLOCKED")
    def test_duplicate_in_same_branch_not_collision(self):
        self.assertEqual(collisions({"a": ["x", "x"]}), {})
    def test_unsafe_path(self):
        for path in ("/root", "../secret", "x/../secret", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                collisions({"a": [path]})
    def test_no_conflict_not_readiness(self):
        result = audit({"a": ["x"]})
        self.assertEqual(result["status"], "NO_PATH_COLLISIONS")
        self.assertIn("not proof", result["note"])

if __name__ == "__main__":
    unittest.main()
