"""Independent completeness *evidence request*, never an attestation issuer.

Grid records immutable observational custody. Root/F must arrange separately
authenticated evidence from an independently pinned authority. A caller's
self-hash, claimed signature, or two equal Bybit scans never establish
exhaustiveness. This module performs no network, SQL, persistence or trading.
"""
import re
from .instrument_universe import UniverseReadError, _need, _sha
from .exchange_roster_epoch import read_root_staged_roster

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def completeness_evidence_request(staged, *, expected_lease_epoch, now_ms):
    """Form a bounded, digest-bound external witness request from frozen data.

    External issuer identity, key custody and signature verification are NOT
    implemented here; Root cannot treat the request as an attestation.
    """
    observation = read_root_staged_roster(
        staged, expected_lease_epoch=expected_lease_epoch, now_ms=now_ms)
    _need(observation["status"] == "INFORMATIONAL"
          and observation["source_status_query"] == "OMITTED"
          and observation["all_exchange_statuses_enumerated"] is False
          and observation["exchange_completeness"] == "NOT_ATTESTED"
          and observation["consumer_cutover_authorized"] is False
          and observation["delisting_authorized"] is False,
          "GRID_ROSTER_EVIDENCE_UNQUALIFIED")
    request = {
        "schema": "market_data.roster-external-evidence-request.v1",
        "status": "EVIDENCE_REQUIRED",
        "venue": "Bybit", "market_type": "linear",
        "source": "GRID_TWO_WALK_OBSERVATION_ONLY",
        "source_status_query": observation["source_status_query"],
        "all_exchange_statuses_enumerated": False,
        "source_epoch": observation["lease_epoch"],
        "roster_sha256": observation["roster_sha256"],
        "observation_fingerprint": observation["dataset_fingerprint"],
        "first_observed_ms": observation["first_observed_ms"],
        "last_observed_ms": observation["last_observed_ms"],
        "record_count": observation["record_count"],
        "page_count": observation["page_count"],
        "witness_requirement": "INDEPENDENT_ROOT_PINNED_EXTERNAL_AUTHORITY",
        "external_witness_verified": False,
        "exchange_completeness": "NOT_ATTESTED",
        "delisting_authorized": False,
        "consumer_cutover_authorized": False,
        "trading_authorized": False,
    }
    return dict(request, challenge_sha256=_sha(request))


def inspect_untrusted_witness_claim(challenge, claim):
    """Check only syntax/binding; NEVER validate a signature or promote trust.

    A real independently pinned verifier is a missing Root/security deliverable.
    This is deliberately not an extensible caller-provided 'verifier=True' seam.
    """
    _need(type(challenge) is dict and type(claim) is dict,
          "GRID_ROSTER_WITNESS_SCHEMA")
    request_keys = {"schema", "status", "venue", "market_type", "source",
                    "source_status_query", "all_exchange_statuses_enumerated",
                    "source_epoch", "roster_sha256", "observation_fingerprint",
                    "first_observed_ms", "last_observed_ms", "record_count",
                    "page_count", "witness_requirement",
                    "external_witness_verified", "exchange_completeness",
                    "delisting_authorized", "consumer_cutover_authorized",
                    "trading_authorized", "challenge_sha256"}
    _need(set(challenge) == request_keys
          and challenge["schema"] == "market_data.roster-external-evidence-request.v1"
          and challenge["status"] == "EVIDENCE_REQUIRED"
          and challenge["venue"] == "Bybit" and challenge["market_type"] == "linear"
          and challenge["source"] == "GRID_TWO_WALK_OBSERVATION_ONLY"
          and challenge["source_status_query"] == "OMITTED"
          and challenge["all_exchange_statuses_enumerated"] is False
          and challenge["witness_requirement"]
              == "INDEPENDENT_ROOT_PINNED_EXTERNAL_AUTHORITY"
          and all(challenge[k] is False for k in (
              "external_witness_verified", "delisting_authorized",
              "consumer_cutover_authorized", "trading_authorized"))
          and challenge["exchange_completeness"] == "NOT_ATTESTED"
          and type(challenge["challenge_sha256"]) is str
          and _HEX.fullmatch(challenge["challenge_sha256"]) is not None
          and challenge["challenge_sha256"] ==
              _sha({k: v for k, v in challenge.items() if k != "challenge_sha256"}),
          "GRID_ROSTER_WITNESS_CHALLENGE_UNQUALIFIED")
    claim_keys = {"schema", "challenge_sha256", "issuer_id",
                  "claimed_roster_sha256", "claimed_complete_count",
                  "claimed_at_ms", "signature_hex"}
    _need(set(claim) == claim_keys
          and claim["schema"] == "market_data.roster-external-claim.v1"
          and type(claim["challenge_sha256"]) is str
          and claim["challenge_sha256"] == challenge["challenge_sha256"]
          and type(claim["claimed_roster_sha256"]) is str
          and claim["claimed_roster_sha256"] == challenge["roster_sha256"]
          and type(claim["claimed_complete_count"]) is int
          and claim["claimed_complete_count"] == challenge["record_count"]
          and type(claim["claimed_at_ms"]) is int
          and challenge["last_observed_ms"] <= claim["claimed_at_ms"]
          <= challenge["last_observed_ms"] + 60000
          and type(claim["issuer_id"]) is str
          and _ID.fullmatch(claim["issuer_id"]) is not None
          and type(claim["signature_hex"]) is str
          and re.fullmatch(r"[0-9a-f]{128}", claim["signature_hex"]) is not None,
          "GRID_ROSTER_WITNESS_CLAIM_UNQUALIFIED")
    return {
        "schema": "market_data.roster-external-evidence-result.v1",
        "status": "INFORMATIONAL",
        "reason": "INDEPENDENT_SIGNATURE_AND_CUSTODY_VERIFIER_NOT_INSTALLED",
        "challenge_sha256": challenge["challenge_sha256"],
        "claim_structure": "VALIDATED_ONLY",
        "issuer_identity": "NOT_VERIFIED",
        "signature_validity": "NOT_VERIFIED",
        "external_witness_verified": False,
        "exchange_completeness": "NOT_ATTESTED",
        "delisting_authorized": False,
        "consumer_cutover_authorized": False,
        "trading_authorized": False,
    }
