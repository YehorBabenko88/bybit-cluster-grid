"""Offline negative security checks. No PC4, LS5, LSA or native calls."""
import unittest
from audit.pc4_independent_security_gate import REQUIRED, NETWORK, evaluate


def checklist(status="UNKNOWN"):
    return {"schema": 1, "checks": {
        key: {"status": status, "evidence_ref": "reviewed/private-record"}
        for key in REQUIRED + NETWORK
    }}


class SecurityGateTests(unittest.TestCase):
    def test_all_unknown_blocks_both(self):
        result = evaluate(checklist())
        self.assertEqual(result["local_review"], "NO_GO")
        self.assertEqual(result["pc4_ls5_review"], "NO_GO")

    def test_every_single_local_blocker_blocks(self):
        for key in REQUIRED:
            with self.subTest(key=key):
                data = checklist("VERIFIED")
                data["checks"][key]["status"] = "UNKNOWN"
                self.assertEqual(evaluate(data)["local_review"], "NO_GO")

    def test_every_network_blocker_blocks_ls5(self):
        for key in NETWORK:
            with self.subTest(key=key):
                data = checklist("VERIFIED")
                data["checks"][key]["status"] = "BLOCKED"
                result = evaluate(data)
                self.assertEqual(result["local_review"], "REVIEWABLE_NOT_AUTHORIZED")
                self.assertEqual(result["pc4_ls5_review"], "NO_GO")

    def test_perfect_self_report_is_not_authorization(self):
        result = evaluate(checklist("VERIFIED"))
        self.assertEqual(result["local_review"], "REVIEWABLE_NOT_AUTHORIZED")
        self.assertEqual(result["pc4_ls5_review"], "REVIEWABLE_NOT_AUTHORIZED")
        for flag in ("physical_attestation", "execution_authorized", "readiness_passed", "schema_2_enabled"):
            self.assertIs(result[flag], False)

    def test_invalid_evidence_rejected(self):
        for key in REQUIRED + NETWORK:
            with self.subTest(key=key):
                data = checklist("VERIFIED")
                data["checks"][key]["evidence_ref"] = ""
                self.assertEqual(evaluate(data)["local_review"], "NO_GO")

    def test_malformed_inputs_rejected(self):
        for data in (None, [], {}, {"schema": True, "checks": {}},
                     {"schema": 1, "checks": {}},
                     {"schema": 1, "checks": {"extra": {}}}):
            with self.subTest(data=str(data)[:60]):
                self.assertEqual(evaluate(data)["local_review"], "NO_GO")

    def test_untrusted_extra_fields_rejected(self):
        data = checklist("VERIFIED")
        data["execution_authorized"] = True
        self.assertEqual(evaluate(data)["local_review"], "NO_GO")
        data = checklist("VERIFIED")
        data["checks"]["full_sid_identity"]["physical_attestation"] = True
        self.assertEqual(evaluate(data)["local_review"], "NO_GO")


if __name__ == "__main__":
    unittest.main()
