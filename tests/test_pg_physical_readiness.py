import unittest
from installer.pg_physical_readiness import REQUIRED, verdict, strict_json


def fixture(status="UNKNOWN"):
    return {"schema": "pg-physical-readiness-1", "head": "a" * 40,
            "checks": {k: {"status": status, "evidence_sha256": "b" * 64} for k in REQUIRED}}


class PhysicalReadinessTests(unittest.TestCase):
    def test_unknown_blocks(self):
        self.assertEqual(verdict(fixture())["verdict"], "BLOCKED")

    def test_all_self_reported_verified_still_blocks(self):
        result = verdict(fixture("VERIFIED"))
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertEqual(result["reason"], "SELF_REPORTED_EVIDENCE_NOT_ATTESTATION")
        self.assertIs(result["physical_execute_authorized"], False)

    def test_each_missing_field_blocks(self):
        for field in REQUIRED:
            with self.subTest(field=field):
                receipt = fixture("VERIFIED")
                del receipt["checks"][field]
                self.assertEqual(verdict(receipt)["verdict"], "BLOCKED")

    def test_each_failed_field_no_go(self):
        for field in REQUIRED:
            with self.subTest(field=field):
                receipt = fixture("VERIFIED")
                receipt["checks"][field]["status"] = "FAIL"
                self.assertEqual(verdict(receipt)["verdict"], "NO-GO")

    def test_forged_authorization_rejected(self):
        receipt = fixture("VERIFIED")
        receipt["physical_execute_authorized"] = True
        self.assertEqual(verdict(receipt)["reason"], "INVALID_RECEIPT")

    def test_missing_digest_rejected(self):
        receipt = fixture("VERIFIED")
        receipt["checks"]["existing_wal_custody"]["evidence_sha256"] = ""
        self.assertEqual(verdict(receipt)["reason"], "INVALID_CHECK")

    def test_duplicate_json_rejected(self):
        with self.assertRaises(ValueError):
            strict_json('{"schema":1,"schema":2}')


if __name__ == "__main__":
    unittest.main()
