"""Offline cross-guest identity collision audit.

Never authorizes VM execution; caller-supplied evidence is untrusted.
"""
from typing import Mapping, Tuple
from .offline_principals import PrincipalEvidence

def audit_cross_guest_isolation(principals: Mapping[str, PrincipalEvidence]) -> Tuple[str, ...]:
    problems = []
    if len(principals) < 2:
        return ("INSUFFICIENT_GUESTS",)
    seen_actual = {}
    seen_token = {}
    for guest, evidence in sorted(principals.items()):
        if not guest or not isinstance(evidence, PrincipalEvidence):
            problems.append(f"{guest}:INVALID_EVIDENCE")
            continue
        if not evidence.actual_sid or not evidence.token_sid:
            problems.append(f"{guest}:SID_UNPROVEN")
            continue
        if evidence.actual_sid != evidence.token_sid:
            problems.append(f"{guest}:TOKEN_USER_MISMATCH")
        for label, sid, seen in (
            ("ACTUAL", evidence.actual_sid, seen_actual),
            ("TOKEN", evidence.token_sid, seen_token),
        ):
            if sid in seen:
                problems.append(f"{label}_SID_REUSED:{seen[sid]}:{guest}")
            else:
                seen[sid] = guest
        if evidence.elevated is True:
            problems.append(f"{guest}:ELEVATED_TOKEN")
        if not evidence.acl_verified or not evidence.independently_attested:
            problems.append(f"{guest}:ISOLATION_UNPROVEN")
    return tuple(problems)
