import unittest
from audit.integration_ci.workflow_attestation import REQUIRED, assess

SHA = "a" * 40

def runs():
    return [{"name": name, "head_sha": SHA, "status": "completed", "conclusion": "success"}
            for name in sorted(REQUIRED)]

class WorkflowAttestationTests(unittest.TestCase):
    def test_all_success_is_ci_only(self):
        result = assess(runs(), SHA)
        self.assertEqual(result["status"], "CI_METADATA_ONLY")
        self.assertIs(result["readiness_passed"], False)
        self.assertIs(result["execution_authorized"], False)
    def test_missing(self):
        self.assertEqual(assess(runs()[:-1], SHA)["status"], "BLOCKED_UNPROVEN")
    def test_cancelled_queued_skipped(self):
        for status, conclusion in (("completed", "cancelled"), ("queued", None),
                                   ("completed", "skipped"), ("in_progress", None)):
            with self.subTest(status=status, conclusion=conclusion):
                data = runs()
                data[0]["status"], data[0]["conclusion"] = status, conclusion
                self.assertEqual(assess(data, SHA)["status"], "BLOCKED_UNPROVEN")
    def test_wrong_sha_and_duplicate(self):
        data = runs()
        data[0]["head_sha"] = "b" * 40
        self.assertEqual(assess(data, SHA)["status"], "BLOCKED_UNPROVEN")
        self.assertEqual(assess(runs() + runs()[:1], SHA)["status"], "BLOCKED_UNPROVEN")
    def test_invalid(self):
        self.assertEqual(assess([], "")["status"], "BLOCKED_UNPROVEN")

if __name__ == "__main__":
    unittest.main()
