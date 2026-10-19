"""Offline evidence binding checks; syntactic consistency is not authenticity.

Does not access guests, filesystems or Windows APIs, and never grants execution.
"""
from dataclasses import dataclass
from typing import Mapping, Tuple
from .sid_validation import valid_sid, valid_integrity_sid, evidence_mapping_types

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
    issues = list(evidence_mapping_types(evidence))
    sid_fields = ("declared_sid", "actual_sid", "token_user_sid", "object_owner_sid")
    for field in sid_fields:
        value = evidence.get(field)
        if not valid_sid(value):
            issues.append(f"{field}:INVALID_SID")
    declared = evidence.get("declared_sid")
    actual = evidence.get("actual_sid")
    token = evidence.get("token_user_sid")
    if all(valid_sid(v) for v in (declared, actual)):
        if declared != actual:
            issues.append("DECLARED_ACTUAL_SID_MISMATCH")
    if all(valid_sid(v) for v in (actual, token)):
        if actual != token:
            issues.append("ACTUAL_TOKEN_SID_MISMATCH")
    groups = evidence.get("token_group_sids")
    if not isinstance(groups, (tuple, list)) or not groups or any(
        not isinstance(g, str) or not valid_sid(g) for g in groups
    ):
        issues.append("INVALID_TOKEN_GROUP_SIDS")
    if isinstance(groups, (tuple, list)) and groups and all(
        isinstance(g, str) and valid_sid(g) for g in groups
    ) and len(groups) != len(set(groups)):
        issues.append("DUPLICATE_TOKEN_GROUP_SID")
    elevation = evidence.get("token_elevation")
    if elevation not in ("limited", "elevated"):
        issues.append("INVALID_TOKEN_ELEVATION")
    elif elevation == "elevated":
        issues.append("ELEVATED_TOKEN_UNSAFE")
    integrity = evidence.get("token_integrity")
    if not valid_integrity_sid(integrity):
        issues.append("INVALID_TOKEN_INTEGRITY")
    elif int(integrity.rsplit("-", 1)[1]) >= 12288:
        issues.append("HIGH_INTEGRITY_TOKEN_UNSAFE")
    privileged_groups = {"S-1-5-32-544", "S-1-5-32-548", "S-1-5-32-549",
                         "S-1-5-32-550", "S-1-5-32-551"}
    if isinstance(groups, (tuple, list)) and any(
        isinstance(g, str) and g in privileged_groups for g in groups
    ):
        issues.append("PRIVILEGED_TOKEN_GROUP_UNSAFE")
    for field in ("effective_read", "effective_write", "effective_write_dac"):
        access = evidence.get(field)
        if type(access) is not bool:
            issues.append(f"{field}:INVALID_EFFECTIVE_ACCESS")
        elif field in ("effective_write", "effective_write_dac") and access:
            issues.append(f"{field}:UNEXPECTED_WRITE_ACCESS")
    return BindingResult(tuple(dict.fromkeys(issues)))
