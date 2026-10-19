"""Offline evidence binding checks; syntactic consistency is not authenticity.

Does not access guests, filesystems or Windows APIs, and never grants execution.
"""
from dataclasses import dataclass
from typing import Mapping, Tuple
import re

_SID_PATTERN = re.compile(r"S-1-(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*))+", re.ASCII)

@dataclass(frozen=True)
class BindingResult:
    issues: Tuple[str, ...]
    status: str = "BLOCKED_UNPROVEN"
    readiness_passed: bool = False
    execution_authorized: bool = False

def audit_evidence_binding(evidence: Mapping[str, object]) -> BindingResult:
    """Reject ambiguous identity bindings before any independent attestation."""
    if not isinstance(evidence, Mapping):
        return BindingResult(("INVALID_EVIDENCE",))
    issues = []
    sid_fields = ("declared_sid", "actual_sid", "token_user_sid", "object_owner_sid")
    for field in sid_fields:
        value = evidence.get(field)
        if not isinstance(value, str) or _SID_PATTERN.fullmatch(value) is None:
            issues.append(f"{field}:INVALID_SID")
    declared = evidence.get("declared_sid")
    actual = evidence.get("actual_sid")
    token = evidence.get("token_user_sid")
    if all(isinstance(v, str) and v.strip() for v in (declared, actual)):
        if declared != actual:
            issues.append("DECLARED_ACTUAL_SID_MISMATCH")
    if all(isinstance(v, str) and v.strip() for v in (actual, token)):
        if actual != token:
            issues.append("ACTUAL_TOKEN_SID_MISMATCH")
    groups = evidence.get("token_group_sids")
    if not isinstance(groups, (tuple, list)) or not groups or any(
        not isinstance(g, str) or _SID_PATTERN.fullmatch(g) is None for g in groups
    ):
        issues.append("INVALID_TOKEN_GROUP_SIDS")
    for field in ("effective_read", "effective_write", "effective_write_dac"):
        if type(evidence.get(field)) is not bool:
            issues.append(f"{field}:INVALID_EFFECTIVE_ACCESS")
    return BindingResult(tuple(issues))
