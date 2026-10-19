"""Versioned, pure read-only boundary audit; not an execution or ownership adapter."""
from __future__ import annotations
import re
from installer.vm_lab_json import canonical, check_value
from installer.vm_lab_plan import CASES, validate_vm_lab_plan
from installer.vm_lab_evidence import digest, draft

VERSION = 1
EXPECTED_CASES = tuple(name for name, _ in CASES)
FALSE_FLAGS = ("execution_authorized", "physical_ready", "readiness_passed")
STAGES = ("vm_plan", "vm_evidence", "attestation", "ownership", "postgres", "preflight", "deployment")
ALLOWED_STATUS = {
    "vm_plan": "BLOCKED",
    "vm_evidence": "BLOCKED",
    "attestation": "BLOCKED",
    "ownership": "BLOCKED",
    "postgres": "VALIDATED_PLAN_ONLY",
    "preflight": "BLOCKED",
    "deployment": "BLOCKED",
}

class ContractBoundaryBlocked(ValueError):
    pass

def _deny(code):
    raise ContractBoundaryBlocked("CONTRACT_" + code)

def _shape(obj, required, optional=(), *, allow_extra=False):
    if type(obj) is not dict or not set(required) <= set(obj) or (not allow_extra and set(obj) - set(required) - set(optional)):
        _deny("SHAPE_INVALID")

def _safe(obj):
    try:
        check_value(obj)
        canonical(obj)
    except (ValueError, TypeError, OverflowError, RecursionError):
        _deny("INPUT_INVALID")

def _blocked(report, stage):
    _shape(report, ("status", "execution_authorized", "physical_ready"), allow_extra=True)
    if report["status"] != ALLOWED_STATUS[stage]:
        _deny("STATUS_PROMOTION")
    for key in FALSE_FLAGS:
        if key in report and report[key] is not False:
            _deny("AUTHORIZATION_PROMOTION")
    if report["execution_authorized"] is not False or report["physical_ready"] is not False:
        _deny("AUTHORIZATION_PROMOTION")
    if "verified_safety_cases" in report and (type(report["verified_safety_cases"]) is not int or report["verified_safety_cases"] != 0):
        _deny("CASE_PROMOTION")
    if report.get("schema2", False) is not False:
        _deny("SCHEMA2_FORBIDDEN")
    if report.get("readiness", "BLOCKED") not in ("BLOCKED",):
        _deny("READINESS_PROMOTION")
    if report.get("physical_status", "NOT_RUN") not in ("NOT_RUN", "BLOCKED_UNPROVEN"):
        _deny("GUEST_EXECUTION_FORBIDDEN")

def _cases(cases):
    if type(cases) is not list or len(cases) != len(EXPECTED_CASES):
        _deny("CASE_COUNT_INVALID")
    for case, name in zip(cases, EXPECTED_CASES):
        _shape(case, ("case", "execution", "assurance"), ("objective",))
        if case["case"] != name or case["execution"] != "NOT_RUN" or case["assurance"] != "BLOCKED_UNPROVEN":
            _deny("GUEST_CASE_UNPROVEN")

def audit_contracts(plan, *, vm_plan=None, vm_evidence=None, attestation=None,
                    ownership=None, postgres=None, preflight=None, deployment=None,
                    bindings=None):
    """Reject unknown fields/unsafe promotions and mixed identity contexts.

    Inputs are *untrusted reports*. Returns metadata-only compatibility, never readiness.
    None means a missing, unverified component, not successful attestation.
    """
    _safe(plan)
    try:
        local = validate_vm_lab_plan(plan)
    except (ValueError, TypeError, KeyError, OverflowError):
        _deny("PLAN_INVALID")
    stages = dict(vm_plan=vm_plan, vm_evidence=vm_evidence, attestation=attestation,
                  ownership=ownership, postgres=postgres, preflight=preflight,
                  deployment=deployment)
    # Never accept a self-reported authorization or readiness signal hidden
    # inside another component's metadata. This is a deny-only scan; it does
    # not attempt to interpret or authenticate component-specific evidence.
    forbidden_keys = frozenset(("execution_authorized", "physical_ready",
                               "readiness_passed", "schema2", "verified_safety_cases"))
    def reject_nested_promotions(value, depth=0):
        if depth > 32:
            _deny("NESTED_DEPTH_INVALID")
        if type(value) is dict:
            for key, child in value.items():
                if key in forbidden_keys:
                    if key == "verified_safety_cases":
                        if type(child) is not int or child != 0:
                            _deny("NESTED_CASE_PROMOTION")
                    elif child is not False:
                        _deny("NESTED_AUTHORIZATION_PROMOTION")
                reject_nested_promotions(child, depth + 1)
        elif type(value) is list:
            for child in value:
                reject_nested_promotions(child, depth + 1)
    # Reports may contain unknown component-specific fields, but cannot
    # carry identity values that contradict the separately supplied binding.
    identity_keys = ("lab_id", "vm_id", "host_id", "image_sha256",
                     "observer_id", "plan_sha256", "pg_run_id",
                     "pg_node_id", "pg_commit_sha")
    def reject_identity_substitution(value, expected, depth=0):
        if depth > 32:
            _deny("NESTED_DEPTH_INVALID")
        if type(value) is dict:
            for key, child in value.items():
                if key in identity_keys and key in expected and child != expected[key]:
                    _deny("NESTED_IDENTITY_MISMATCH")
                reject_identity_substitution(child, expected, depth + 1)
        elif type(value) is list:
            for child in value:
                reject_identity_substitution(child, expected, depth + 1)
    for stage, report in stages.items():
        if report is None:
            continue
        _safe(report)
        reject_nested_promotions(report)
        _blocked(report, stage)
        if stage in ("vm_plan", "vm_evidence", "attestation"):
            _shape(report, ("negative_cases",), allow_extra=True)
            _cases(report["negative_cases"])
        if stage == "vm_plan":
            if canonical(report) != canonical(local):
                _deny("PLAN_REPORT_MISMATCH")
        if stage == "vm_evidence":
            if report.get("authentication") != "UNVERIFIED" or report.get("integrity") != "MATCH_METADATA_ONLY":
                _deny("EVIDENCE_TRUST_PROMOTION")
        if stage == "attestation":
            if report.get("authentication") != "TEST_KEY_ONLY" or report.get("signature_result") != "VERIFIED_PUBLIC_TEST_FIXTURE":
                _deny("ATTESTATION_ROLE_PROMOTION")
        if stage == "ownership":
            if report.get("assurance") != "SYNTHETIC_ONLY" or report.get("backend") not in ("MODEL", "NATIVE_FIXTURE"):
                _deny("OWNERSHIP_CAPABILITY_PROMOTION")
            if report.get("synthetic_result") not in ("BLOCKED", "PASS"):
                _deny("OWNERSHIP_RESULT_INVALID")
        if stage == "postgres":
            if report.get("postgres_major") != 16 or report.get("node_id") in ("LS5", "LS7"):
                _deny("PG_METADATA_INVALID")
    if bindings is None:
        if any(stages[s] is not None for s in ("vm_evidence", "attestation", "postgres", "preflight", "deployment")):
            _deny("BINDINGS_REQUIRED")
    else:
        _safe(bindings)
        _shape(bindings, ("schema", "plan_sha256", "lab_id", "vm_id", "host_id",
                           "image_sha256", "observer_id", "challenge", "pg_run_id", "pg_node_id", "pg_commit_sha"))
        if type(bindings["schema"]) is not int or bindings["schema"] != VERSION:
            _deny("VERSION_INVALID")
        for k, expected in (("plan_sha256", digest(plan)), ("lab_id", plan["lab_id"]),
                            ("vm_id", plan["vm_id"]), ("host_id", plan["host"]["id"]),
                            ("image_sha256", plan["image"]["sha256"])):
            if bindings[k] != expected:
                _deny("BINDING_MISMATCH")
        from installer.vm_test_attestation import _challenge, _ROOTS
        try:
            _challenge(bindings["challenge"])
        except (ValueError, TypeError, KeyError):
            _deny("CHALLENGE_INVALID")
        if bindings["observer_id"] != _ROOTS["test-observer-v1"][1]:
            _deny("OBSERVER_INVALID")
        for k in ("pg_run_id", "pg_node_id", "pg_commit_sha"):
            if type(bindings[k]) is not str or not re.fullmatch(
                "[0-9a-f]{32}" if k == "pg_run_id" else
                "[A-Z][A-Z0-9_-]{0,14}" if k == "pg_node_id" else "[0-9a-f]{40}", bindings[k]):
                _deny("PG_BINDING_INVALID")
        if bindings["pg_node_id"] in ("LS5", "LS7"):
            _deny("PROTECTED_NODE")
        # The keys above are audit-envelope identifiers. Check them only
        # where explicitly present; missing provenance remains UNPROVEN.
        for stage, report in stages.items():
            if report is not None:
                reject_identity_substitution(report, bindings)
        for stage in ("postgres", "preflight"):
            report = stages[stage]
            if report is not None:
                for key, value in (("run_id", bindings["pg_run_id"]),
                                   ("node_id", bindings["pg_node_id"])):
                    if report.get(key) != value:
                        _deny("PG_IDENTITY_MISMATCH")
                if stage == "preflight" and report.get("commit_sha") != bindings["pg_commit_sha"]:
                    _deny("COMMIT_MISMATCH")
        if stages["vm_evidence"] is not None:
            expected = draft(plan, bindings["observer_id"])
            if "plan_sha256" in vm_evidence and vm_evidence["plan_sha256"] != digest(plan):
                _deny("EVIDENCE_PLAN_MISMATCH")
            if "payload_sha256" in vm_evidence and vm_evidence["payload_sha256"] != expected["payload_sha256"]:
                _deny("EVIDENCE_PAYLOAD_MISMATCH")
        if attestation is not None:
            # Reports never prove their own signature/nonce. Caller must retain the
            # verifier's consumed replay state and signed envelope separately.
            if "challenge" in attestation and attestation["challenge"] != bindings["challenge"]:
                _deny("CHALLENGE_MISMATCH")
            if "observer_id" in attestation and attestation["observer_id"] != bindings["observer_id"]:
                _deny("OBSERVER_MISMATCH")
    # Explicit identity contradictions are rejectable, but matching strings
    # alone are not proof that two reports came from the same run.
    return {
        "schema": VERSION, "status": "BLOCKED", "execution_authorized": False,
        "physical_ready": False, "readiness_passed": False,
        "verified_safety_cases": 0, "schema2": False,
        "guest_cases": [{"case": k, "execution": "NOT_RUN", "assurance": "BLOCKED_UNPROVEN"} for k in EXPECTED_CASES],
        "matrix": {k: ("PRESENT_UNTRUSTED_METADATA" if v is not None else "MISSING_UNPROVEN")
                   for k, v in stages.items()},
        "trust_level": "UNVERIFIED_METADATA_ONLY",
        "blockers": ["NO_CROSS_COMPONENT_AUTHORITY", "INDEPENDENT_PROOF_NOT_IMPLEMENTED",
                     "REPORT_ORIGIN_AND_CHALLENGE_NOT_CRYPTOGRAPHICALLY_BOUND",
                     "CROSS_COMPONENT_REPLAY_NOT_DURABLY_PREVENTED",
                     "NO_SCHEMA2_OR_PHYSICAL_EXECUTOR", "ALL_GUEST_CASES_NOT_RUN"],
    }
