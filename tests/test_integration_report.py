import unittest
from audit.integration_ci.integration_report import report, to_json
from audit.integration_ci.workflow_attestation import REQUIRED

SHA = "c" * 40
RUNS = [{"name": name, "head_sha": SHA, "status": "completed", "conclusion": "success"} for name in REQUIRED]

class IntegrationReportTests(unittest.TestCase):
    def test_all_green_still_blocked(self):
        result = report({"vm": ["vm/a.py"], "pg": ["pg/b.py"]}, RUNS, SHA)
        self.assertEqual(result["status"], "BLOCKED_UNPROVEN")
        self.assertFalse(result["readiness_passed"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["schema_2_enabled"])
        self.assertEqual(result["vm_case_status"], "NOT_RUN")
        self.assertIn("BLOCKED_UNPROVEN", to_json(result))
    def test_overlap_explicit_blocker(self):
        result = report({"vm": ["same"], "pg": ["same"]}, RUNS, SHA)
        self.assertIn("overlapping paths require human reconciliation", result["blockers"])
    def test_missing_ci_blocker(self):
        result = report({}, [], SHA)
        self.assertIn("required CI evidence incomplete", result["blockers"])

if __name__ == "__main__":
    unittest.main()
