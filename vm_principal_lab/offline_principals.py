"""Offline-only Windows principal evidence model. Never probes a host or authorizes execution."""
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple
from .sid_validation import valid_sid, principal_shape_issues, valid_group_sids

CASES = tuple(f"VM-NEG-{i:02d}" for i in range(1, 13))
BLOCKED = "BLOCKED_UNPROVEN"
NOT_RUN = "NOT_RUN"

@dataclass(frozen=True)
class PrincipalEvidence:
    declared_sid: str
    actual_sid: Optional[str] = None
    token_sid: Optional[str] = None
    elevated: Optional[bool] = None
    group_sids: Tuple[str, ...] = ()
    acl_verified: bool = False
    independently_attested: bool = False

@dataclass(frozen=True)
class IsolationDecision:
    status: str = BLOCKED
    readiness_passed: bool = False
    execution_authorized: bool = False
    cases: Tuple[Tuple[str, str], ...] = tuple((case, NOT_RUN) for case in CASES)
    reasons: Tuple[str, ...] = ()

def assess_offline(principals: Mapping[str, PrincipalEvidence], hostile_admin: bool = False) -> IsolationDecision:
    """Classify supplied evidence; even complete evidence cannot authorize VM execution."""
    reasons = []
    if type(hostile_admin) is not bool:
        reasons.append("INVALID_HOSTILE_ADMIN_BOOLEAN")
    if hostile_admin is True:
        reasons.append("HOSTILE_ADMIN_STOP")
    if not isinstance(principals, Mapping):
        return IsolationDecision(reasons=tuple(reasons + ["INVALID_PRINCIPAL_COLLECTION"]))
    if len(principals) < 2:
        reasons.append("DISTINCT_PRINCIPALS_MISSING")
    actual = []
    for name, evidence in sorted(principals.items(), key=lambda item: str(item[0])):
        if type(name) is not str or not name or not isinstance(evidence, PrincipalEvidence):
            reasons.append(f"{name}:INVALID_EVIDENCE")
            continue
        reasons.extend(f"{name}:{item}" for item in principal_shape_issues(evidence))
        if not valid_sid(evidence.declared_sid):
            reasons.append(f"{name}:DECLARED_SID_MISSING")
        if not valid_sid(evidence.actual_sid) or not valid_sid(evidence.token_sid):
            reasons.append(f"{name}:ACTUAL_TOKEN_UNPROVEN")
        elif evidence.actual_sid != evidence.token_sid:
            reasons.append(f"{name}:TOKEN_SID_MISMATCH")
        if valid_sid(evidence.declared_sid) and valid_sid(evidence.actual_sid) and evidence.declared_sid != evidence.actual_sid:
            reasons.append(f"{name}:DECLARED_ACTUAL_SID_MISMATCH")
        if evidence.elevated is True:
            reasons.append(f"{name}:UNEXPECTED_ELEVATED_TOKEN")
        if type(evidence.elevated) is not bool:
            reasons.append(f"{name}:ELEVATION_UNPROVEN")
        if evidence.acl_verified is not True:
            reasons.append(f"{name}:ACL_UNPROVEN")
        if evidence.independently_attested is not True:
            reasons.append(f"{name}:ATTESTATION_MISSING")
        if not valid_group_sids(evidence.group_sids):
            reasons.append(f"{name}:GROUP_MEMBERSHIP_UNPROVEN")
        if valid_sid(evidence.actual_sid):
            actual.append(evidence.actual_sid)
    if len(actual) != len(set(actual)):
        reasons.append("SHARED_ACTUAL_SID")
    return IsolationDecision(reasons=tuple(reasons or ["OFFLINE_MODEL_CANNOT_AUTHORIZE_EXECUTION"]))
