"""Offline VM case contract tests; no host inspection or execution."""
from vm_principal_lab.negative_cases import NEGATIVE_CASES, validate_protocol
from vm_principal_lab.offline_principals import CASES, assess_offline

def test_protocol_has_twelve_unique_cases():
    assert validate_protocol()
    assert tuple(case.case_id for case in NEGATIVE_CASES) == CASES

def test_each_case_requires_explicit_evidence_but_remains_not_run():
    for case in NEGATIVE_CASES:
        assert case.required_evidence
        assert case.expected == "NOT_RUN"

def test_hostile_admin_never_grants_execution():
    result = assess_offline({}, hostile_admin=True)
    assert result.reasons[0] == "HOSTILE_ADMIN_STOP"
    assert result.execution_authorized is False
    assert result.readiness_passed is False
    assert all(status == "NOT_RUN" for _, status in result.cases)
