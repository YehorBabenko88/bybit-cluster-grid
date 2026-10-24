import hashlib
import io
import json
import unittest
import zipfile

from installer.ls5_e2e_acceptance import (
    PHASES, FAULTS, AcceptanceBlocked, inspect_e2e, inspect_g0_g1, verify_zip_bytes
)

HEAD = "e25197b169ef0e5f37b5bd0030ee4a97b13965e2"


def make_report():
    return {
        "head": HEAD, "run_id": 101, "attempt": 1,
        "environment": "DISPOSABLE_SYNTHETIC", "artifact_sha256": "a" * 64,
        "independent_readback": False,
        "phases": [{"name": name, "status": "PASS", "evidence": "producer-claim"}
                   for name in PHASES],
        "faults": [{"name": name, "status": "PASS", "evidence": "producer-claim"}
                   for name in FAULTS],
    }


class E2EAcceptanceTests(unittest.TestCase):
    def inspect(self, data):
        return inspect_e2e(json.dumps(data).encode(), expected_head=HEAD,
                           expected_run=101, expected_attempt=1)

    def test_full_producer_claim_never_go(self):
        result = self.inspect(make_report())
        self.assertTrue(result["producer_claims_complete"])
        self.assertFalse(result["lab_go"])
        self.assertFalse(result["artifact_bytes_verified"])

    def test_faults_and_phases_incomplete(self):
        for field in ("phases", "faults"):
            for state in ("NOT_RUN", "BLOCKED", "FAIL"):
                data = make_report()
                data[field][0]["status"] = state
                self.assertIn(data[field][0]["name"],
                              self.inspect(data)["unverified_or_incomplete"])

    def test_head_attempt_and_duplicate_phase(self):
        for field, value in (("head", "f" * 40), ("run_id", 102),
                             ("attempt", 2), ("environment", "LS5_PHYSICAL"),
                             ("independent_readback", 1)):
            data = make_report()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(AcceptanceBlocked):
                self.inspect(data)
        data = make_report()
        data["phases"][1] = data["phases"][0]
        with self.assertRaises(AcceptanceBlocked):
            self.inspect(data)

    def test_rehashed_zip_and_fake_entry(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("junit.xml", b"safe")
        raw = out.getvalue()
        result = verify_zip_bytes(raw, expected_digest=hashlib.sha256(raw).hexdigest(),
                                  expected_files={"junit.xml": hashlib.sha256(b"safe").hexdigest()})
        self.assertFalse(result["origin_authenticated"])
        for files in ({"junit.xml": "f" * 64}, {"../escape": "a" * 64}, {}):
            with self.subTest(files=files), self.assertRaises(AcceptanceBlocked):
                verify_zip_bytes(raw, expected_digest=hashlib.sha256(raw).hexdigest(),
                                 expected_files=files)

    def test_exact_head_run_attempt_positive_and_tampering(self):
        valid = make_report()
        self.assertFalse(self.inspect(valid)["lab_go"])
        for field, replacement in (("head", "b" * 40),
                                   ("run_id", 102), ("attempt", 2)):
            forged = dict(valid, **{field: replacement})
            with self.subTest(field=field), self.assertRaises(AcceptanceBlocked):
                self.inspect(forged)

    def test_self_consistent_zip_is_not_provenance(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("results.xml", b'<testsuite tests="26" failures="0"/>')
            z.writestr("events.jsonl", b'{"status":"PASS"}\\n')
        raw = out.getvalue()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            digests = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
        verdict = verify_zip_bytes(raw, expected_digest=hashlib.sha256(raw).hexdigest(),
                                   expected_files=digests)
        self.assertTrue(verdict["zip_consistent"])
        self.assertFalse(verdict["origin_authenticated"])
        self.assertFalse(verdict["lab_go"])
        tampered = bytearray(raw)
        tampered[-8] ^= 1
        with self.assertRaises(AcceptanceBlocked):
            verify_zip_bytes(bytes(tampered), expected_digest=hashlib.sha256(raw).hexdigest(),
                             expected_files=digests)

    def test_g0_g1_queued_and_forged_head(self):
        pins = {n: HEAD for n in range(238, 243)}
        rows = [{"pr": n, "head": HEAD, "workflow": "queued", "run_id": n,
                 "attempt": 1, "artifact_sha256": "a" * 64,
                 "artifact_bytes_verified": False, "contract_test": False}
                for n in pins]
        self.assertEqual(len(inspect_g0_g1(rows, expected_heads=pins)["g0_g1_unverified"]), 5)
        green = [dict(x, workflow="success", artifact_bytes_verified=True,
                      contract_test=True) for x in rows]
        self.assertFalse(inspect_g0_g1(green, expected_heads=pins)["lab_go"])
        forged = [dict(x) for x in green]
        forged[0]["head"] = "f" * 40
        with self.assertRaises(AcceptanceBlocked):
            inspect_g0_g1(forged, expected_heads=pins)


if __name__ == "__main__":
    unittest.main()
