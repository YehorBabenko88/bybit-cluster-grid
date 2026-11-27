"""Exact source checks of non-authoritative independent completeness contract."""
import copy
import unittest
from dataclasses import replace
from test_exchange_roster_observed_route_round35 import staged_observation
from market_data_v2.roster_completeness_contract import (
    completeness_evidence_request, inspect_untrusted_witness_claim)
from market_data_v2.instrument_universe import UniverseReadError, _sha


class CompletenessEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.staged = staged_observation()
        self.request = completeness_evidence_request(
            self.staged, expected_lease_epoch="opaque-root-epoch",
            now_ms=1800000000000)
        self.claim = {
            "schema": "market_data.roster-external-claim.v1",
            "challenge_sha256": self.request["challenge_sha256"],
            "issuer_id": "pretend-independent-issuer",
            "claimed_roster_sha256": self.request["roster_sha256"],
            "claimed_complete_count": self.request["record_count"],
            "claimed_at_ms": 1800000000000,
            "signature_hex": "a"*128,
        }

    def test_challenge_is_only_a_request(self):
        self.assertEqual(self.request["status"], "EVIDENCE_REQUIRED")
        self.assertEqual(self.request["exchange_completeness"], "NOT_ATTESTED")
        self.assertEqual(self.request["source_status_query"], "OMITTED")
        self.assertFalse(self.request["all_exchange_statuses_enumerated"])
        self.assertFalse(self.request["external_witness_verified"])
        self.assertFalse(self.request["delisting_authorized"])
        self.assertFalse(self.request["consumer_cutover_authorized"])
        self.assertEqual(self.request["challenge_sha256"],
                         _sha({k:v for k,v in self.request.items()
                               if k != "challenge_sha256"}))

    def test_self_claimed_perfect_signature_cannot_authorize(self):
        result = inspect_untrusted_witness_claim(self.request, self.claim)
        self.assertEqual(result["status"], "INFORMATIONAL")
        self.assertEqual(result["signature_validity"], "NOT_VERIFIED")
        self.assertEqual(result["exchange_completeness"], "NOT_ATTESTED")
        self.assertFalse(result["delisting_authorized"])
        self.assertFalse(result["consumer_cutover_authorized"])
        self.assertFalse(result["trading_authorized"])

    def test_unrelated_claim_is_denied(self):
        for key, value in (("claimed_roster_sha256", "f"*64),
                           ("claimed_complete_count", 2),
                           ("challenge_sha256", "0"*64),
                           ("claimed_at_ms", 1800000070000),
                           ("signature_hex", "invalid"),
                           ("issuer_id", "<script>")):
            with self.subTest(key=key), self.assertRaises(UniverseReadError):
                bad = copy.deepcopy(self.claim)
                bad[key] = value
                inspect_untrusted_witness_claim(self.request, bad)

    def test_rehashed_claimed_root_approval_fails_closed(self):
        bad = copy.deepcopy(self.request)
        bad["external_witness_verified"] = True
        bad["challenge_sha256"] = _sha({
            k:v for k,v in bad.items() if k != "challenge_sha256"})
        with self.assertRaises(UniverseReadError):
            inspect_untrusted_witness_claim(bad, self.claim)

    def test_untrusted_extra_fields_cannot_grant_authority(self):
        bad = dict(self.claim, delisting_authorized=True)
        with self.assertRaises(UniverseReadError):
            inspect_untrusted_witness_claim(self.request, bad)

    def test_forged_all_status_claim_cannot_be_upgraded(self):
        bad = copy.deepcopy(self.request)
        bad["all_exchange_statuses_enumerated"] = True
        bad["challenge_sha256"] = _sha({
            k: v for k, v in bad.items() if k != "challenge_sha256"})
        with self.assertRaises(UniverseReadError):
            inspect_untrusted_witness_claim(bad, self.claim)

    def test_wrong_root_epoch_cannot_issue_challenge(self):
        with self.assertRaises(UniverseReadError):
            completeness_evidence_request(
                self.staged, expected_lease_epoch="different-epoch",
                now_ms=1800000000000)

    def test_corrupted_immutable_stage_cannot_issue_challenge(self):
        invalid = replace(self.staged, payload_sha256="0"*64)
        with self.assertRaises(UniverseReadError):
            completeness_evidence_request(
                invalid, expected_lease_epoch="opaque-root-epoch",
                now_ms=1800000000000)


if __name__ == "__main__":
    unittest.main()
