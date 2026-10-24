"""Offline tests for PostgreSQL 18 evidence receipts; no database access."""
import hashlib
import json
import unittest
from installer.ls5_pg_readiness import assess, FIELDS, loads_strict, verify_payload


def make_receipt():
    return {"schema": "ls5-pg-readiness-1", "head": "e25197b169ef0e5f37b5bd0030ee4a97b13965e2",
            "physical": False, "checks": {
                key: {"status": "UNKNOWN", "evidence_sha256": ""} for key in FIELDS}}


class ReceiptIntegrity(unittest.TestCase):
    def test_unknown_without_evidence_stays_blocked(self):
        self.assertEqual(assess(make_receipt())["status"], "BLOCKED")

    def test_corrupt_sha_rejected(self):
        receipt = make_receipt()
        receipt["checks"]["backup_chain"] = {"status": "VERIFIED", "evidence_sha256": "bad"}
        self.assertEqual(assess(receipt)["status"], "BLOCKED")

    def test_digest_tampering_changes_digest(self):
        original = b'{"records":[{"id":1,"amount":3}]}'
        altered = b'{"records":[{"id":1,"amount":4}]}'
        self.assertNotEqual(hashlib.sha256(original).digest(), hashlib.sha256(altered).digest())

    def test_receipt_requires_exact_payload_bytes(self):
        receipt = make_receipt()
        original = b"backup-manifest-original"
        receipt["checks"]["backup_chain"] = {
            "status": "VERIFIED", "evidence_sha256": hashlib.sha256(original).hexdigest()}
        self.assertTrue(verify_payload(receipt, "backup_chain", original))
        self.assertFalse(verify_payload(receipt, "backup_chain", original + b"-tampered"))
        self.assertFalse(verify_payload(receipt, "backup_chain", original.decode()))
        self.assertFalse(verify_payload(receipt, "not-a-check", original))

    def test_payload_validator_rejects_physical_promotion(self):
        receipt = make_receipt()
        payload = b"offline-evidence"
        receipt["checks"]["backup_chain"] = {
            "status": "VERIFIED", "evidence_sha256": hashlib.sha256(payload).hexdigest()}
        self.assertTrue(verify_payload(receipt, "backup_chain", payload))
        receipt["physical"] = True
        self.assertFalse(verify_payload(receipt, "backup_chain", payload))
        receipt["physical"] = False
        receipt["schema"] = "untrusted-schema"
        self.assertFalse(verify_payload(receipt, "backup_chain", payload))
        receipt["schema"] = "ls5-pg-readiness-1"
        receipt["checks"]["backup_chain"]["extra"] = "injected"
        self.assertFalse(verify_payload(receipt, "backup_chain", payload))

    def test_partial_receipt_cannot_verify_single_payload(self):
        receipt = make_receipt()
        payload = b"legitimate-offline-blob"
        receipt["checks"]["backup_chain"] = {
            "status": "VERIFIED", "evidence_sha256": hashlib.sha256(payload).hexdigest()}
        self.assertTrue(verify_payload(receipt, "backup_chain", payload))
        del receipt["checks"]["db_roles"]
        self.assertFalse(verify_payload(receipt, "backup_chain", payload))

    def test_duplicate_receipt_key_rejected(self):
        with self.assertRaises(ValueError):
            loads_strict('{"checks":{},"checks":{}}')

    def test_untrusted_physical_promotion_rejected(self):
        receipt = make_receipt()
        receipt["physical"] = True
        self.assertEqual(assess(receipt)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
