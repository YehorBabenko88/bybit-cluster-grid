from vm_principal_lab.cross_guest_isolation import audit_cross_guest_isolation
from vm_principal_lab.offline_principals import PrincipalEvidence

def principal(sid, **overrides):
    values = dict(declared_sid=sid, actual_sid=sid, token_sid=sid,
                  elevated=False, acl_verified=True, independently_attested=True)
    values.update(overrides)
    return PrincipalEvidence(**values)

def test_distinct_limited_guest_identities_have_no_collisions():
    assert audit_cross_guest_isolation({"a": principal("SID-A"), "b": principal("SID-B")}) == ()

def test_reused_sid_across_guests_rejected():
    errors = audit_cross_guest_isolation({"a": principal("SID-A"), "b": principal("SID-A")})
    assert "ACTUAL_SID_REUSED:a:b" in errors
    assert "TOKEN_SID_REUSED:a:b" in errors

def test_elevated_token_rejected():
    errors = audit_cross_guest_isolation({"a": principal("SID-A", elevated=True),
                                          "b": principal("SID-B")})
    assert "a:ELEVATED_TOKEN" in errors

def test_unverified_attestation_rejected():
    errors = audit_cross_guest_isolation({"a": principal("SID-A", independently_attested=False),
                                          "b": principal("SID-B")})
    assert "a:ISOLATION_UNPROVEN" in errors

def test_missing_sid_cannot_count_as_distinct():
    errors = audit_cross_guest_isolation({"a": principal("SID-A", actual_sid=None),
                                          "b": principal("SID-B")})
    assert "a:SID_UNPROVEN" in errors
