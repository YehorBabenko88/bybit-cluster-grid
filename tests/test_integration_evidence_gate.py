import unittest
from audit.integration_ci.evidence_gate import validate

def blocked():
    return {"status": "BLOCKED_UNPROVEN", "readiness_passed": False,
            "execution_authorized": False, "schema_2_enabled": False,
            "vm_cases": [{"id": f"VM-{i:02}", "status": "NOT_RUN"} for i in range(1, 13)]}

class EvidenceGateTests(unittest.TestCase):
    def test_blocked_baseline(self):
        self.assertEqual(validate(blocked()), [])
    def test_false_pass(self):
        for field in ("readiness_passed", "execution_authorized", "schema_2_enabled"):
            for value in (True, None, "false", 0):
                with self.subTest(field=field, value=value):
                    data = blocked()
                    data[field] = value
                    self.assertTrue(validate(data))
    def test_case_mutations(self):
        for status in ("PASS", "SKIPPED", "BLOCKED_UNPROVEN", None):
            data = blocked()
            data["vm_cases"][0]["status"] = status
            self.assertTrue(validate(data))
    def test_missing_duplicate_cases(self):
        data = blocked()
        data["vm_cases"].pop()
        self.assertTrue(validate(data))
        data = blocked()
        data["vm_cases"][1]["id"] = data["vm_cases"][0]["id"]
        self.assertTrue(validate(data))
    def test_missing_evidence(self):
        self.assertTrue(validate({}))
        self.assertTrue(validate(None))

if __name__ == "__main__":
    unittest.main()
