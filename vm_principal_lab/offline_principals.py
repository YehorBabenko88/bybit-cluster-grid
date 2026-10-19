"""Offline-only Windows principal evidence model. Never probes a host or authorizes execution."""
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

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
    if hostile_admin:
        reasons.append("HOSTILE_ADMIN_STOP")
    if len(principals) < 2:
        reasons.append("DISTINCT_PRINCIPALS_MISSING")
    actual = []
    for name, evidence in sorted(principals.items()):
        if not evidence.declared_sid:
            reasons.append(f"{name}:DECLARED_SID_MISSING")
        if not evidence.actual_sid or not evidence.token_sid:
            reasons.append(f"{name}:ACTUAL_TOKEN_UNPROVEN")
        elif evidence.actual_sid != evidence.token_sid:
            reasons.append(f"{name}:TOKEN_SID_MISMATCH")
        if evidence.elevated is None:
            reasons.append(f"{name}:ELEVATION_UNPROVEN")
        if not evidence.acl_verified:
            reasons.append(f"{name}:ACL_UNPROVEN")
        if not evidence.independently_attested:
            reasons.append(f"{name}:ATTESTATION_MISSING")
        if evidence.actual_sid:
            actual.append(evidence.actual_sid)
    if len(actual) != len(set(actual)):
        reasons.append("SHARED_ACTUAL_SID")
    return IsolationDecision(reasons=tuple(reasons or ["OFFLINE_MODEL_CANNOT_AUTHORIZE_EXECUTION"]))
