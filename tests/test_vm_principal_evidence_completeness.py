from vm_principal_lab.evidence_completeness import (
    REQUIRED_FIELDS, audit_evidence_completeness,
)

def valid_evidence():
    evidence = {field: "synthetic" for field in REQUIRED_FIELDS}
    evidence.update(declared_sid="S-1-5-21-101", actual_sid="S-1-5-21-101",
                    token_user_sid="S-1-5-21-101", object_owner_sid="S-1-5-18",
                    token_group_sids=("S-1-5-32-545",),
                    token_elevation="limited", token_integrity="S-1-16-8192",
                    effective_read=False, effective_write=False, effective_write_dac=False)
    return evidence

def test_empty_evidence_reports_all_missing():
    result = audit_evidence_completeness({})
    assert result.missing == REQUIRED_FIELDS
    assert result.complete is False
    assert result.execution_authorized is False

def test_each_required_field_is_enforced():
    evidence = valid_evidence()
    for field in REQUIRED_FIELDS:
        partial = dict(evidence)
        del partial[field]
        result = audit_evidence_completeness(partial)
        assert field in result.missing
        assert result.status == "BLOCKED_UNPROVEN"

def test_complete_synthetic_evidence_never_authorizes():
    evidence = valid_evidence()
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
    evidence = valid_evidence()
    evidence["token_group_sids"] = []
    assert "token_group_sids" in audit_evidence_completeness(evidence).missing

def test_nonboolean_effective_access_is_not_evidence():
    evidence = {field: "synthetic" for field in REQUIRED_FIELDS}
    evidence.update(effective_read="false", effective_write=0, effective_write_dac=None)
    missing = audit_evidence_completeness(evidence).missing
    assert {"effective_read", "effective_write", "effective_write_dac"} <= set(missing)

def test_p2_r4_overflow_is_not_complete_evidence():
    evidence = valid_evidence()
    evidence["actual_sid"] = "S-1-5-4294967296"
    result = audit_evidence_completeness(evidence)
    assert "actual_sid" in result.missing
    assert result.complete is False and result.execution_authorized is False

def test_p2_r5_string_elevation_and_group_lists_not_complete():
    evidence = valid_evidence()
    evidence["token_elevation"] = "false"
    evidence["token_group_sids"] = ["S-1-5-32-545"]
    result = audit_evidence_completeness(evidence)
    assert "token_elevation" in result.missing
    assert "token_group_sids" in result.missing
    assert result.complete is False
