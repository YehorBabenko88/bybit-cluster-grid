from vm_principal_lab.cross_guest_isolation import audit_cross_guest_isolation
from vm_principal_lab.offline_principals import PrincipalEvidence

def principal(sid, **overrides):
    values = dict(declared_sid=sid, actual_sid=sid, token_sid=sid,
                  elevated=False, group_sids=("S-1-5-32-545",),
                  acl_verified=True, independently_attested=True)
    values.update(overrides)
    return PrincipalEvidence(**values)

def test_distinct_limited_guest_identities_have_no_collisions():
    assert audit_cross_guest_isolation({"a": principal("S-1-5-21-101"), "b": principal("S-1-5-21-102")}) == ()

def test_reused_sid_across_guests_rejected():
    errors = audit_cross_guest_isolation({"a": principal("S-1-5-21-101"), "b": principal("S-1-5-21-101")})
    assert "ACTUAL_SID_REUSED:a:b" in errors
    assert "TOKEN_SID_REUSED:a:b" in errors

def test_elevated_token_rejected():
    errors = audit_cross_guest_isolation({"a": principal("S-1-5-21-101", elevated=True),
                                          "b": principal("S-1-5-21-102")})
    assert "a:ELEVATED_TOKEN" in errors

def test_unverified_attestation_rejected():
    errors = audit_cross_guest_isolation({"a": principal("S-1-5-21-101", independently_attested=False),
                                          "b": principal("S-1-5-21-102")})
    assert "a:ISOLATION_UNPROVEN" in errors

def test_missing_sid_cannot_count_as_distinct():
    errors = audit_cross_guest_isolation({"a": principal("S-1-5-21-101", actual_sid=None),
                                          "b": principal("S-1-5-21-102")})
    assert "a:SID_UNPROVEN" in errors

def test_shared_privileged_group_is_rejected():
    errors = audit_cross_guest_isolation({
        "a": principal("S-1-5-21-101", group_sids=("S-1-5-32-544",)),
        "b": principal("S-1-5-21-102", group_sids=("S-1-5-32-544",)),
    })
    assert "SHARED_PRIVILEGED_GROUP:a:b:S-1-5-32-544" in errors
    assert "a:PRIVILEGED_GROUP:S-1-5-32-544" in errors

def test_missing_groups_and_elevation_are_unproven():
    errors = audit_cross_guest_isolation({
        "a": principal("S-1-5-21-101", group_sids=(), elevated=None),
        "b": principal("S-1-5-21-102"),
    })
    assert "a:GROUP_MEMBERSHIP_UNPROVEN" in errors
    assert "a:ELEVATION_UNPROVEN" in errors

def test_declared_actual_sid_drift_is_rejected():
    errors = audit_cross_guest_isolation({
        "a": principal("S-1-5-21-101", declared_sid="S-1-5-21-103"),
        "b": principal("S-1-5-21-102"),
    })
    assert "a:DECLARED_ACTUAL_MISMATCH" in errors

def test_missing_sid_does_not_hide_privilege_and_acl_failures():
    errors = audit_cross_guest_isolation({
        "a": principal("S-1-5-21-101", actual_sid=None, elevated=True,
                       group_sids=("S-1-5-32-544",), acl_verified=False),
        "b": principal("S-1-5-21-102"),
    })
    assert "a:SID_UNPROVEN" in errors
    assert "a:ELEVATED_TOKEN" in errors
    assert "a:PRIVILEGED_GROUP:S-1-5-32-544" in errors
    assert "a:ISOLATION_UNPROVEN" in errors

def test_invalid_collection_and_guest_keys_fail_closed():
    assert audit_cross_guest_isolation(None) == ("INVALID_PRINCIPAL_COLLECTION",)
    errors = audit_cross_guest_isolation({1: principal("S-1-5-21-101"), "b": principal("S-1-5-21-102")})
    assert "1:INVALID_EVIDENCE" in errors

def test_missing_sids_are_not_falsely_reported_as_shared():
    errors = audit_cross_guest_isolation({
        "a": principal("S-1-5-21-101", actual_sid=None),
        "b": principal("S-1-5-21-102", actual_sid=None),
    })
    assert "a:SID_UNPROVEN" in errors and "b:SID_UNPROVEN" in errors
    assert not any("ACTUAL_SID_REUSED" in issue for issue in errors)
