"""Fail-closed validation of untrusted offline readiness-shaped documents.

This is an audit gate, not a deployment authorization API.
"""
from typing import Any, Mapping, Tuple

FORBIDDEN_TRUE = ("readiness_passed", "execution_authorized", "deployment_authorized")
FORBIDDEN_STATES = {"READY", "PASS", "PASSED", "AUTHORIZED", "RUNNING", "COMPLETE"}

def audit_readiness_document(document: Mapping[str, Any]) -> Tuple[str, ...]:
    errors = []
    if not isinstance(document, Mapping):
        return ("INVALID_DOCUMENT",)
    if document.get("status") != "BLOCKED_UNPROVEN":
        errors.append("STATUS_NOT_BLOCKED")
    for key in FORBIDDEN_TRUE:
        if document.get(key) is not False:
            errors.append(f"{key.upper()}_NOT_FALSE")
    cases = document.get("cases")
    if not isinstance(cases, Mapping):
        errors.append("CASES_MISSING")
    else:
        expected = {f"VM-NEG-{i:02d}" for i in range(1, 13)}
        if set(cases) != expected:
            errors.append("CASE_SET_MISMATCH")
        for case_id, value in sorted(cases.items()):
            if value != "NOT_RUN":
                errors.append(f"{case_id}:NOT_NOT_RUN")
    if document.get("hostile_admin") is True and document.get("hostile_admin_action") != "STOP":
        errors.append("HOSTILE_ADMIN_STOP_MISSING")
    for key in ("readiness", "deployment_state", "execution_state"):
        if str(document.get(key, "")).upper() in FORBIDDEN_STATES:
            errors.append(f"{key.upper()}_PROMOTION")
    return tuple(errors)
