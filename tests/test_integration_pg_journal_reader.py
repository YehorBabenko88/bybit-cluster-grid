import json
import unittest
from audit.integration_ci.pg_journal_reader import inspect_journal_bytes

DIGEST = "a" * 64

def journal(*states, digest=DIGEST):
    return "".join(json.dumps({"schema": 1, "plan_sha256": digest, "state": state}, separators=(",", ":")) + "\n" for state in states)

class PgJournalReaderTests(unittest.TestCase):
    def test_legal_transitions_are_metadata_only(self):
        for states in (("PREPARED",), ("PREPARED", "COMMITTED"), ("PREPARED", "RETIRED"), ("PREPARED", "COMMITTED", "RETIRED")):
            with self.subTest(states=states):
                result = inspect_journal_bytes(journal(*states), DIGEST)
                self.assertTrue(result["metadata_valid"])
                self.assertFalse(result["execution_authorized"])
                self.assertFalse(result["physical_ownership_verified"])
    def test_fail_closed(self):
        bad = [
            journal("COMMITTED"), journal("PREPARED", "PREPARED"),
            journal("PREPARED", "RETIRED", "COMMITTED"),
            journal("PREPARED", digest="b"*64),
            journal("PREPARED")[:-1], "{bad}\n",
            json.dumps({"schema": 2, "plan_sha256": DIGEST, "state": "PREPARED"}) + "\n",
            json.dumps({"schema": 1, "plan_sha256": DIGEST, "state": "PREPARED", "execution_authorized": True}) + "\n",
            "x" * 4097,
        ]
        for value in bad:
            with self.subTest(value=value[:60]):
                self.assertFalse(inspect_journal_bytes(value, DIGEST)["metadata_valid"])

    def test_duplicate_json_keys_rejected(self):
        for early in ('"schema":2,', '"plan_sha256":"wrong",', '"state":"RETIRED",'):
            record = '{' + early + '"schema":1,"plan_sha256":"' + DIGEST + '","state":"PREPARED"}\n'
            result = inspect_journal_bytes(record, DIGEST)
            self.assertIn("DUPLICATE_JSON_KEY", result["errors"])

    def test_powershell_canonical_bytes(self):
        good = journal("PREPARED")
        mutants = (
            good.replace(',"state"', ', "state"'),
            good.replace('"schema":1,"plan_sha256":"' + DIGEST + '"',
                         '"plan_sha256":"' + DIGEST + '","schema":1'),
            good.replace("PREPARED", r"PREPAR\u0045D"),
            good.replace("\n", "\r\n"),
            good.replace('"state"', r'"st\u0061te"'),
            b"\xef\xbb\xbf" + good.encode("utf-8"),
        )
        for bad in mutants:
            with self.subTest(bad=str(bad)[:80]):
                result = inspect_journal_bytes(bad, DIGEST)
                self.assertFalse(result["metadata_valid"])
                self.assertFalse(result["byte_contract_verified"])

    def test_unicode_returns_fixed_error(self):
        for bad in ("\ud800\n", b"\xff\n", b"\xed\xa0\x80\n"):
            result = inspect_journal_bytes(bad, DIGEST)
            self.assertIn("INVALID_UNICODE", result["errors"])
            self.assertEqual(result["status"], "BLOCKED_UNPROVEN")

    def test_canonical_lifecycle_not_authority(self):
        for states, phase in ((("PREPARED",), "PREPARED"),
                              (("PREPARED", "COMMITTED"), "COMMITTED"),
                              (("PREPARED", "RETIRED"), "RETIRED")):
            result = inspect_journal_bytes(journal(*states).encode("utf-8"), DIGEST)
            self.assertTrue(result["byte_contract_verified"])
            self.assertEqual(result["lifecycle_phase"], phase)
            self.assertFalse(result["execution_authorized"])
            self.assertFalse(result["physical_ownership_verified"])

    def test_invalid_digest_and_types(self):
        for value in (None, [], "", "z"*64):
            self.assertFalse(inspect_journal_bytes(journal("PREPARED"), value)["metadata_valid"])

    def test_nonascii_record_digest_never_raises(self):
        for invalid in ("é" * 64, "a" * 63 + "é", "\\ud800"):
            with self.subTest(invalid=repr(invalid)):
                record = journal("PREPARED", digest=invalid)
                result = inspect_journal_bytes(record, DIGEST)
                self.assertEqual(result["status"], "BLOCKED_UNPROVEN")
                self.assertFalse(result["metadata_valid"])
                self.assertFalse(result["execution_authorized"])
                self.assertIn("INVALID_RECORD_DIGEST", result["errors"])

if __name__ == "__main__":
    unittest.main()
