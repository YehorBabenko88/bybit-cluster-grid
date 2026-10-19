"""Standalone offline adversarial checks. Never create a VM, service or database."""
import copy
import json
from pathlib import Path

import pytest

from installer.contract_boundary_audit import audit_contracts, ContractBoundaryBlocked
from installer.vm_lab_evidence import digest
from installer.vm_lab_plan import validate_vm_lab_plan


def fixture():
    return json.loads((Path(__file__).resolve().parents[1] /
                       "installer/tests/vm-lab-plan.example.json").read_text(encoding="utf8"))


def bindings(p):
    return {"schema": 1, "plan_sha256": digest(p), "lab_id": p["lab_id"],
            "vm_id": p["vm_id"], "host_id": p["host"]["id"],
            "image_sha256": p["image"]["sha256"],
            "observer_id": "55555555-5555-4555-8555-555555555555",
            "challenge": {"session_id": "77777777-7777-4777-8777-777777777777",
                          "nonce": "a" * 64, "sequence": 1,
                          "code_sha256": "b" * 64, "artifact_sha256": "c" * 64},
            "pg_run_id": "d" * 32, "pg_node_id": "TESTNODE",
            "pg_commit_sha": "e" * 40}


def test_missing_stages_never_mean_readiness():
    p = fixture()
    result = audit_contracts(p)
    assert result["status"] == "BLOCKED"
    assert all(result[k] is False for k in
               ("physical_ready", "readiness_passed", "execution_authorized", "schema2"))
    assert len(result["guest_cases"]) == 12
    assert set(result["matrix"].values()) == {"MISSING_UNPROVEN"}


def test_original_vm_plan_report_not_promoted():
    p = fixture()
    result = audit_contracts(p, vm_plan=validate_vm_lab_plan(p))
    assert result["matrix"]["vm_plan"] == "PRESENT_UNTRUSTED_METADATA"


@pytest.mark.parametrize("field", ["execution_authorized", "physical_ready", "readiness_passed",
                                   "status", "verified_safety_cases", "schema2",
                                   "negative_cases", "blockers"])
def test_forged_vm_pass_rejected(field):
    p = fixture()
    report = validate_vm_lab_plan(p)
    report[field] = (True if field in ("execution_authorized", "physical_ready", "readiness_passed", "schema2")
                     else "PASS" if field == "status"
                     else 1 if field == "verified_safety_cases"
                     else [] if field == "negative_cases" else ["FAKE"] if field == "blockers" else None)
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, vm_plan=report)


@pytest.mark.parametrize("field,value", [
    ("plan_sha256", "f" * 64), ("lab_id", "88888888-8888-4888-8888-888888888888"),
    ("vm_id", "99999999-9999-4999-8999-999999999999"),
    ("host_id", "LAB-HOST-99999999-9999-4999-8999-999999999999"),
    ("image_sha256", "1" * 64), ("observer_id", "9" * 36),
    ("pg_node_id", "LS5"), ("pg_run_id", "1" * 32), ("pg_commit_sha", "wrong"),
    ("schema", 2)])
def test_mismatched_binding_rejected(field, value):
    p = fixture()
    b = bindings(p)
    b[field] = value
    # A different standalone PG run id can be valid; the binding is not proof
    if field == "pg_run_id":
        with pytest.raises(ContractBoundaryBlocked):
            audit_contracts(p, bindings=b, postgres={"status": "VALIDATED_PLAN_ONLY",
                    "execution_authorized": False, "physical_ready": False,
                    "postgres_major": 16, "run_id": "d" * 32, "node_id": "TESTNODE"})
    else:
        with pytest.raises(ContractBoundaryBlocked):
            audit_contracts(p, bindings=b)


@pytest.mark.parametrize("field,value", [
    ("session_id", "a"), ("nonce", "bad"), ("sequence", True),
    ("sequence", -1), ("code_sha256", "bad"), ("artifact_sha256", "bad")])
def test_bad_challenge_rejected(field, value):
    p = fixture()
    b = bindings(p)
    b["challenge"][field] = value
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, bindings=b)


@pytest.mark.parametrize("stage,report", [
    ("ownership", {"status": "BLOCKED", "execution_authorized": False, "physical_ready": False,
                   "assurance": "REAL_OWNER", "backend": "MODEL", "synthetic_result": "PASS"}),
    ("ownership", {"status": "PASS", "execution_authorized": False, "physical_ready": False,
                   "assurance": "SYNTHETIC_ONLY", "backend": "MODEL", "synthetic_result": "PASS"}),
    ("postgres", {"status": "VALIDATED_PLAN_ONLY", "execution_authorized": True,
                  "physical_ready": False, "postgres_major": 16, "node_id": "TESTNODE"}),
    ("preflight", {"status": "READY", "execution_authorized": False, "physical_ready": False}),
    ("deployment", {"status": "SYNTHETIC_PASS", "execution_authorized": False, "physical_ready": False}),
    ("attestation", {"status": "BLOCKED", "execution_authorized": False, "physical_ready": False,
                     "negative_cases": [], "authentication": "PRODUCTION"}),
])
def test_cross_adapter_promotion_rejected(stage, report):
    p = fixture()
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, bindings=bindings(p), **{stage: report})


@pytest.mark.parametrize("stage", ["vm_evidence", "attestation", "postgres", "preflight", "deployment"])
def test_cross_component_requires_explicit_bindings(stage):
    p = fixture()
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, **{stage: {"status": "BLOCKED",
                                     "physical_ready": False, "execution_authorized": False}})


def test_validated_postgres_is_not_capability():
    p = fixture()
    b = bindings(p)
    pg = {"status": "VALIDATED_PLAN_ONLY", "physical_ready": False,
          "execution_authorized": False, "run_id": b["pg_run_id"],
          "node_id": b["pg_node_id"], "postgres_major": 16}
    result = audit_contracts(p, bindings=b, postgres=pg)
    assert result["status"] == "BLOCKED" and result["matrix"]["postgres"] == "PRESENT_UNTRUSTED_METADATA"


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema2=True),
    lambda p: p["accounts"][1].update(token_sid=p["accounts"][0]["token_sid"]),
    lambda p: p["approval"].update(approved=False),
    lambda p: p["integration"].update(clipboard=True),
    lambda p: p["network"].update(ssh=True),
])
def test_vm_plan_violation_blocks(mutation):
    p = fixture()
    mutation(p)
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p)


def test_unknown_binding_field_rejected():
    p = fixture()
    b = bindings(p)
    b["physical_ready"] = True
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, bindings=b)


def test_no_mutation_of_caller_data():
    p = fixture()
    b = bindings(p)
    before = copy.deepcopy((p, b))
    audit_contracts(p, bindings=b)
    assert (p, b) == before


@pytest.mark.parametrize("stage,field,value", [
    ("vm_evidence", "plan_sha256", "0" * 64),
    ("vm_evidence", "payload_sha256", "0" * 64),
    ("attestation", "observer_id", "99999999-9999-4999-8999-999999999999"),
    ("attestation", "challenge", {"session_id": "77777777-7777-4777-8777-777777777777",
                                    "nonce": "f" * 64, "sequence": 1,
                                    "code_sha256": "b" * 64, "artifact_sha256": "c" * 64}),
])
def test_explicit_foreign_report_provenance_is_rejected(stage, field, value):
    p = fixture()
    b = bindings(p)
    report = {"status": "BLOCKED", "execution_authorized": False, "physical_ready": False,
              "negative_cases": [{"case": case["case"], "execution": "NOT_RUN",
                                  "assurance": "BLOCKED_UNPROVEN"}
                                 for case in validate_vm_lab_plan(p)["negative_cases"]]}
    if stage == "vm_evidence":
        report.update(authentication="UNVERIFIED", integrity="MATCH_METADATA_ONLY")
    else:
        report.update(authentication="TEST_KEY_ONLY",
                      signature_result="VERIFIED_PUBLIC_TEST_FIXTURE")
    report[field] = value
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, bindings=b, **{stage: report})


@pytest.mark.parametrize("key,value", [
    ("execution_authorized", True),
    ("physical_ready", True),
    ("readiness_passed", True),
    ("schema2", True),
    ("verified_safety_cases", 12),
])
def test_nested_metadata_cannot_smuggle_authorization(key, value):
    p = fixture()
    report = validate_vm_lab_plan(p)
    report["extra_untrusted_metadata"] = {"opaque": [{"inner": {key: value}}]}
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, vm_plan=report)


def test_deeply_nested_untrusted_report_is_rejected():
    p = fixture()
    report = validate_vm_lab_plan(p)
    nested = {"value": False}
    for _ in range(34):
        nested = {"nested": nested}
    report["extra_untrusted_metadata"] = nested
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, vm_plan=report)


@pytest.mark.parametrize("field", [
    "lab_id", "vm_id", "host_id", "image_sha256",
    "observer_id", "plan_sha256", "pg_run_id", "pg_node_id", "pg_commit_sha",
])
def test_nested_cross_component_identity_substitution_rejected(field):
    p = fixture()
    b = bindings(p)
    report = validate_vm_lab_plan(p)
    report["opaque_component_metadata"] = {"nested": [{field: "FORGED"}]}
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, vm_plan=report, bindings=b)


def test_repeated_matching_reports_never_become_authorized():
    p = fixture()
    b = bindings(p)
    report = validate_vm_lab_plan(p)
    first = audit_contracts(p, vm_plan=report, bindings=b)
    second = audit_contracts(p, vm_plan=copy.deepcopy(report), bindings=copy.deepcopy(b))
    assert first == second
    assert "CROSS_COMPONENT_REPLAY_NOT_DURABLY_PREVENTED" in second["blockers"]
    assert second["execution_authorized"] is False
    assert second["physical_ready"] is False
    assert second["verified_safety_cases"] == 0


def test_metadata_trust_level_cannot_be_confused_with_authentication():
    p = fixture()
    result = audit_contracts(p, vm_plan=validate_vm_lab_plan(p), bindings=bindings(p))
    assert result["trust_level"] == "UNVERIFIED_METADATA_ONLY"
    assert result["status"] == "BLOCKED"
    assert result["readiness_passed"] is False
    assert "NO_CROSS_COMPONENT_AUTHORITY" in result["blockers"]


@pytest.mark.parametrize("stage", ["vm_plan", "ownership"])
def test_present_metadata_never_claims_provenance_or_replay_protection(stage):
    p = fixture()
    if stage == "vm_plan":
        result = audit_contracts(p, vm_plan=validate_vm_lab_plan(p), bindings=bindings(p))
    else:
        result = audit_contracts(p)
    for flag in ("provenance_verified", "replay_protection_verified",
                 "cross_component_authority", "execution_authorized", "physical_ready"):
        assert result[flag] is False
    assert result["trust_level"] == "UNVERIFIED_METADATA_ONLY"


@pytest.mark.parametrize("flag", [
    "provenance_verified", "replay_protection_verified", "cross_component_authority"
])
@pytest.mark.parametrize("nested", [False, True])
def test_forged_provenance_or_authority_is_denied(flag, nested):
    p = fixture()
    report = validate_vm_lab_plan(p)
    if nested:
        report["untrusted_component_data"] = {"nested": {flag: True}}
    else:
        report[flag] = True
    with pytest.raises(ContractBoundaryBlocked):
        audit_contracts(p, vm_plan=report)


def test_test_key_metadata_never_proves_guest_execution():
    p = fixture()
    result = audit_contracts(p, vm_plan=validate_vm_lab_plan(p), bindings=bindings(p))
    assert result["guest_execution_verified"] is False
    assert result["test_key_attestation_is_production_proof"] is False
    assert all(case["execution"] == "NOT_RUN" for case in result["guest_cases"])
    assert all(case["assurance"] == "BLOCKED_UNPROVEN" for case in result["guest_cases"])
