import unittest
from audit.integration_ci.job_evidence import inspect_jobs, EXPECTED_JOBS

SHA = "a" * 40

def jobs():
    return [{"name": name, "status": "completed", "conclusion": "success",
             "steps": [{"name": "Offline negative evidence contract tests", "conclusion": "success"}]}
            for name in sorted(EXPECTED_JOBS)]

class JobEvidenceTests(unittest.TestCase):
    def test_success_still_no_authority(self):
        result = inspect_jobs(jobs(), SHA)
        self.assertEqual(result["status"], "CI_JOB_METADATA_ONLY")
        self.assertIs(result["execution_authorized"], False)
        self.assertIs(result["readiness_passed"], False)
    def test_negative_cases(self):
        for mutation in ("missing", "duplicate", "skipped", "cancelled", "missing_steps", "skipped_step", "unexpected", "no_test_step"):
            with self.subTest(mutation=mutation):
                data = jobs()
                if mutation == "missing": data.pop()
                elif mutation == "duplicate": data.append(dict(data[0]))
                elif mutation == "skipped": data[0]["conclusion"] = "skipped"
                elif mutation == "cancelled": data[0]["status"] = "cancelled"
                elif mutation == "missing_steps": data[0]["steps"] = []
                elif mutation == "skipped_step": data[0]["steps"][0]["conclusion"] = "skipped"
                elif mutation == "unexpected": data.append({"name": "unknown"})
                elif mutation == "no_test_step": data[0]["steps"][0]["name"] = "Unrelated passing step"
                self.assertEqual(inspect_jobs(data, SHA)["status"], "BLOCKED_UNPROVEN")
    def test_bad_sha_and_policy_override(self):
        self.assertEqual(inspect_jobs(jobs(), "z" * 40)["status"], "BLOCKED_UNPROVEN")
        self.assertEqual(inspect_jobs(jobs(), SHA, frozenset())["status"], "BLOCKED_UNPROVEN")

if __name__ == "__main__":
    unittest.main()
