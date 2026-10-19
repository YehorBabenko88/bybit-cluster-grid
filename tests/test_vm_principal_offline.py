"""Pure offline regression tests; no Windows APIs, VM, services, or deployment."""
from vm_principal_lab.offline_principals import (
    BLOCKED, NOT_RUN, CASES, PrincipalEvidence, assess_offline,
)

def _assert_blocked(result):
    assert result.status == BLOCKED
    assert result.readiness_passed is False
    assert result.execution_authorized is False
    assert len(result.cases) == 12
    assert all(status == NOT_RUN for _, status in result.cases)

def test_empty_evidence_fails_closed():
    result = assess_offline({})
    _assert_blocked(result)
    assert "DISTINCT_PRINCIPALS_MISSING" in result.reasons

def test_declared_is_not_actual():
    result = assess_offline({"guest": PrincipalEvidence(declared_sid="S-1-5-21-1")})
    _assert_blocked(result)
    assert "guest:ACTUAL_TOKEN_UNPROVEN" in result.reasons

def test_shared_sid_is_rejected():
    evidence = PrincipalEvidence("S-1-5-21-10", "S-1-5-21-11", "S-1-5-21-11", False, ("S-1-5-32-545",), True, True)
    result = assess_offline({"a": evidence, "b": evidence})
    _assert_blocked(result)
    assert "SHARED_ACTUAL_SID" in result.reasons

def test_token_mismatch_is_rejected():
    evidence = PrincipalEvidence("S-1-5-21-10", "S-1-5-21-12", "S-1-5-21-13", False, ("S-1-5-32-545",), True, True)
    result = assess_offline({"a": evidence, "b": PrincipalEvidence("S-1-5-21-22", "S-1-5-21-22", "S-1-5-21-22", False, ("S-1-5-32-545",), True, True)})
    _assert_blocked(result)
    assert "a:TOKEN_SID_MISMATCH" in result.reasons

def test_hostile_admin_always_stops():
    result = assess_offline({}, hostile_admin=True)
    _assert_blocked(result)
    assert "HOSTILE_ADMIN_STOP" in result.reasons

def test_even_attested_distinct_principals_do_not_authorize_execution():
    result = assess_offline({
        "a": PrincipalEvidence("S-1-5-21-21", "S-1-5-21-21", "S-1-5-21-21", False, ("S-1-5-32-545",), True, True),
        "b": PrincipalEvidence("S-1-5-21-22", "S-1-5-21-22", "S-1-5-21-22", False, ("S-1-5-32-545",), True, True),
    })
    _assert_blocked(result)
    assert result.reasons == ("OFFLINE_MODEL_CANNOT_AUTHORIZE_EXECUTION",)

def test_declared_actual_sid_drift_is_explicitly_rejected():
    result = assess_offline({
        "a": PrincipalEvidence("S-1-5-21-15", "S-1-5-21-16", "S-1-5-21-16", False, ("S-1-5-32-545",), True, True),
        "b": PrincipalEvidence("S-1-5-21-22", "S-1-5-21-22", "S-1-5-21-22", False, ("S-1-5-32-545",), True, True),
    })
    _assert_blocked(result)
    assert "a:DECLARED_ACTUAL_SID_MISMATCH" in result.reasons

def test_elevated_guest_token_is_explicitly_rejected():
    result = assess_offline({
        "a": PrincipalEvidence("S-1-5-21-21", "S-1-5-21-21", "S-1-5-21-21", True, (), True, True),
        "b": PrincipalEvidence("S-1-5-21-22", "S-1-5-21-22", "S-1-5-21-22", False, ("S-1-5-32-545",), True, True),
    })
    _assert_blocked(result)
    assert "a:UNEXPECTED_ELEVATED_TOKEN" in result.reasons
