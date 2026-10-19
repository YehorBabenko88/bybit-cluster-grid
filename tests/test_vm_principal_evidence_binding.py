from vm_principal_lab.evidence_binding import audit_evidence_binding

def evidence(**overrides):
    values = dict(declared_sid="S-1-5-21-100", actual_sid="S-1-5-21-100",
                  token_user_sid="S-1-5-21-100", object_owner_sid="S-1-5-21-100",
                  token_group_sids=("S-1-5-32-545",), effective_read=True,
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
    for groups in ((), ["valid", ""], "S-1-5-32-545", [None]):
        assert "INVALID_TOKEN_GROUP_SIDS" in audit_evidence_binding(
            evidence(token_group_sids=groups)).issues

def test_effective_access_requires_real_booleans():
    issues = audit_evidence_binding(evidence(effective_read="true",
                                            effective_write=0,
                                            effective_write_dac=None)).issues
    assert all(f"{field}:INVALID_EFFECTIVE_ACCESS" in issues for field in (
        "effective_read", "effective_write", "effective_write_dac"))

def test_non_mapping_is_blocked():
    result = audit_evidence_binding(None)
    assert result.issues == ("INVALID_EVIDENCE",)
    assert result.execution_authorized is False
