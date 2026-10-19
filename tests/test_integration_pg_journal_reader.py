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
    def test_invalid_digest_and_types(self):
        for value in (None, [], "", "z"*64):
            self.assertFalse(inspect_journal_bytes(journal("PREPARED"), value)["metadata_valid"])

if __name__ == "__main__":
    unittest.main()
