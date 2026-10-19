import unittest
from audit.integration_ci.cross_contracts import inspect_contracts

def baseline():
    return (
        {"mode": "PlanOnly", "physical_cases_status": "NOT_RUN", "ownership_session": "s1"},
        {"mode": "read-only", "schema_version": 1, "ownership_session": "s1"},
        {"authenticated": True, "session": "s1", "readiness_passed": False, "execution_authorized": False},
    )

class CrossContractsTests(unittest.TestCase):
    def test_baseline(self):
        self.assertEqual(inspect_contracts(*baseline()), [])
    def test_fail_closed_mutations(self):
        changes = [
            (0, "mode", "Execute"), (0, "physical_cases_status", "PASS"),
            (1, "mode", "write"), (1, "schema_version", 2),
            (1, "schema_version", True), (1, "ownership_session", "s2"),
            (2, "authenticated", False), (2, "session", "s2"),
            (2, "readiness_passed", True), (2, "execution_authorized", True),
        ]
        for index, key, value in changes:
            with self.subTest(index=index, key=key, value=value):
                args = baseline()
                args[index][key] = value
                self.assertTrue(inspect_contracts(*args))
    def test_invalid_inputs(self):
        self.assertTrue(inspect_contracts(None, {}, {}))

if __name__ == "__main__":
    unittest.main()
