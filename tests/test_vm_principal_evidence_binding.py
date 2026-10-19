from vm_principal_lab.evidence_binding import audit_evidence_binding

def evidence(**overrides):
    values = dict(declared_sid="S-1-5-21-100", actual_sid="S-1-5-21-100",
                  token_user_sid="S-1-5-21-100", object_owner_sid="S-1-5-21-100",
                  token_group_sids=("S-1-5-32-545",), token_elevation="limited",
                  token_integrity="S-1-16-8192", effective_read=True,
                  effective_write=False, effective_write_dac=False)
    values.update(overrides)
    return values

def test_consistent_synthetic_evidence_still_cannot_authorize():
    result = audit_evidence_binding(evidence())
    assert result.issues == ()
    assert result.status == "BLOCKED_UNPROVEN"
    assert result.readiness_passed is False
    assert result.execution_authorized is False

def test_declared_actual_mismatch():
    assert "DECLARED_ACTUAL_SID_MISMATCH" in audit_evidence_binding(
        evidence(declared_sid="S-1-5-21-999")).issues

def test_actual_token_mismatch():
    assert "ACTUAL_TOKEN_SID_MISMATCH" in audit_evidence_binding(
        evidence(token_user_sid="S-1-5-21-999")).issues

def test_malformed_group_sids():
    for groups in ((), ["S-1-5-32-545", ""], "S-1-5-32-545", [None]):
        assert "INVALID_TOKEN_GROUP_SIDS" in audit_evidence_binding(
            evidence(token_group_sids=groups)).issues

def test_effective_access_requires_real_booleans():
    issues = audit_evidence_binding(evidence(effective_read="true",
                                            effective_write=0,
                                            effective_write_dac=None)).issues
    assert all(f"{field}:INVALID_EFFECTIVE_ACCESS" in issues for field in (
        "effective_read", "effective_write", "effective_write_dac"))

def test_noncanonical_sid_is_rejected():
    for invalid in ("synthetic", "s-1-5-21-100", "S-1-05-21-100",
                    "S-1-5-21-100 ", "S-1-5-21--100"):
        assert "actual_sid:INVALID_SID" in audit_evidence_binding(
            evidence(actual_sid=invalid)).issues

def test_malformed_owner_sid_is_rejected_without_implying_same_owner_as_user():
    issues = audit_evidence_binding(evidence(object_owner_sid="not-a-sid")).issues
    assert "object_owner_sid:INVALID_SID" in issues
    assert audit_evidence_binding(evidence(object_owner_sid="S-1-5-18")).issues == ()

def test_non_mapping_is_blocked():
    result = audit_evidence_binding(None)
    assert result.issues == ("INVALID_EVIDENCE",)
    assert result.execution_authorized is False

def test_elevated_token_is_explicitly_unsafe():
    issues = audit_evidence_binding(evidence(token_elevation="elevated")).issues
    assert "ELEVATED_TOKEN_UNSAFE" in issues

def test_unknown_elevation_and_integrity_rejected():
    issues = audit_evidence_binding(evidence(token_elevation="unknown", token_integrity="high")).issues
    assert "INVALID_TOKEN_ELEVATION" in issues
    assert "INVALID_TOKEN_INTEGRITY" in issues

def test_duplicate_token_groups_rejected():
    issues = audit_evidence_binding(evidence(token_group_sids=("S-1-5-32-545", "S-1-5-32-545"))).issues
    assert "DUPLICATE_TOKEN_GROUP_SID" in issues

def test_effective_write_is_rejected_even_when_boolean():
    issues = audit_evidence_binding(evidence(effective_write=True)).issues
    assert "effective_write:UNEXPECTED_WRITE_ACCESS" in issues

def test_effective_write_dac_is_rejected_even_when_boolean():
    issues = audit_evidence_binding(evidence(effective_write_dac=True)).issues
    assert "effective_write_dac:UNEXPECTED_WRITE_ACCESS" in issues

def test_read_only_evidence_does_not_prove_authorization():
    result = audit_evidence_binding(evidence(effective_read=True, effective_write=False,
                                            effective_write_dac=False))
    assert result.issues == ()
    assert result.readiness_passed is False
    assert result.execution_authorized is False
