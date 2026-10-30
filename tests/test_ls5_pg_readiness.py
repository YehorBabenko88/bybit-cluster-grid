import unittest
from installer.ls5_pg_readiness import FIELDS, assess, loads_strict


def sample(status="UNKNOWN"):
    return {"schema": "ls5-pg-readiness-1", "head": "e25197b169ef0e5f37b5bd0030ee4a97b13965e2",
            "physical": False, "checks": {k: {"status": status, "evidence_sha256": "a" * 64} for k in FIELDS}}


class PgReadinessTests(unittest.TestCase):
    def test_unknown_is_blocked(self):
        self.assertEqual(assess(sample())["status"], "BLOCKED")

    def test_each_failure_is_fail(self):
        for key in FIELDS:
            with self.subTest(key=key):
                data = sample("VERIFIED")
                data["checks"][key]["status"] = "FAIL"
                self.assertEqual(assess(data)["status"], "FAIL")

    def test_each_unknown_is_blocked(self):
        for key in FIELDS:
            with self.subTest(key=key):
                data = sample("VERIFIED")
                data["checks"][key]["status"] = "UNKNOWN"
                self.assertEqual(assess(data)["status"], "BLOCKED")

    def test_even_all_verified_cannot_authorize(self):
        r = assess(sample("VERIFIED"))
        self.assertEqual(r["status"], "OFFLINE_REVIEW_COMPLETE")
        self.assertIs(r["physical_verified"], False)
        self.assertIs(r["deployment_authorized"], False)
        self.assertIs(r["sql_authorized"], False)

    def test_physical_promotion_rejected(self):
        d = sample("VERIFIED")
        d["physical"] = True
        self.assertEqual(assess(d)["status"], "BLOCKED")

    def test_missing_evidence_rejected(self):
        d = sample("VERIFIED")
        d["checks"]["backup_chain"]["evidence_sha256"] = ""
        self.assertEqual(assess(d)["status"], "BLOCKED")

    def test_unknown_and_extra_keys_rejected(self):
        d = sample()
        del d["checks"]["db_roles"]
        self.assertEqual(assess(d)["status"], "BLOCKED")
        d = sample()
        d["checks"]["extra"] = {"status": "VERIFIED", "evidence_sha256": "a" * 64}
        self.assertEqual(assess(d)["status"], "BLOCKED")

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):
            loads_strict('{"schema":1,"schema":2}')

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            loads_strict('{"value":NaN}')


if __name__ == "__main__":
    unittest.main()
