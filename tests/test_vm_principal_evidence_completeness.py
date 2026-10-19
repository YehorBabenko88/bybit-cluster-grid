from vm_principal_lab.evidence_completeness import (
    REQUIRED_FIELDS, audit_evidence_completeness,
)

def test_empty_evidence_reports_all_missing():
    result = audit_evidence_completeness({})
    assert result.missing == REQUIRED_FIELDS
    assert result.complete is False
    assert result.execution_authorized is False

def test_each_required_field_is_enforced():
    evidence = {field: "synthetic" for field in REQUIRED_FIELDS}
    evidence.update(effective_read=False, effective_write=False, effective_write_dac=False)
    for field in REQUIRED_FIELDS:
        partial = dict(evidence)
        del partial[field]
        result = audit_evidence_completeness(partial)
        assert field in result.missing
        assert result.status == "BLOCKED_UNPROVEN"

def test_complete_synthetic_evidence_never_authorizes():
    evidence = {field: "synthetic" for field in REQUIRED_FIELDS}
    evidence.update(effective_read=False, effective_write=False, effective_write_dac=False)
    result = audit_evidence_completeness(evidence)
    assert result.complete is True
    assert result.missing == ()
    assert result.readiness_passed is False
    assert result.execution_authorized is False

def test_null_and_blank_fields_rejected():
    result = audit_evidence_completeness({
        "actual_sid": None, "source_id": " ", "observed_at": "",
    })
    assert "actual_sid" in result.missing
    assert "source_id" in result.missing
    assert "observed_at" in result.missing

def test_empty_group_collection_is_missing():
    evidence = {field: "synthetic" for field in REQUIRED_FIELDS}
    evidence.update(effective_read=False, effective_write=False, effective_write_dac=False)
    evidence["token_group_sids"] = []
    assert "token_group_sids" in audit_evidence_completeness(evidence).missing

def test_nonboolean_effective_access_is_not_evidence():
    evidence = {field: "synthetic" for field in REQUIRED_FIELDS}
    evidence.update(effective_read="false", effective_write=0, effective_write_dac=None)
    missing = audit_evidence_completeness(evidence).missing
    assert {"effective_read", "effective_write", "effective_write_dac"} <= set(missing)
