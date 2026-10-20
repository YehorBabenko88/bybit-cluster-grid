"""Offline cross-guest identity collision audit.

Never authorizes VM execution; caller-supplied evidence is untrusted.
"""
from typing import Mapping, Tuple
from .offline_principals import PrincipalEvidence
from .sid_validation import principal_shape_issues, valid_sid, valid_group_sids

def audit_cross_guest_isolation(principals: Mapping[str, PrincipalEvidence]) -> Tuple[str, ...]:
    problems = []
    if not isinstance(principals, Mapping):
        return ("INVALID_PRINCIPAL_COLLECTION",)
    if len(principals) < 2:
        return ("INSUFFICIENT_GUESTS",)
    seen_actual = {}
    seen_token = {}
    privileged_groups = {"S-1-5-32-544", "S-1-5-32-548", "S-1-5-32-549",
                         "S-1-5-32-550", "S-1-5-32-551"}
    seen_privileged = {}
    for guest, evidence in sorted(principals.items(), key=lambda item: str(item[0])):
        if not isinstance(guest, str) or not guest or not isinstance(evidence, PrincipalEvidence):
            problems.append(f"{guest}:INVALID_EVIDENCE")
            continue
        problems.extend(f"{guest}:{error}" for error in principal_shape_issues(evidence))
        if not valid_sid(evidence.actual_sid) or not valid_sid(evidence.token_sid):
            problems.append(f"{guest}:SID_UNPROVEN")
        elif evidence.actual_sid != evidence.token_sid:
            problems.append(f"{guest}:TOKEN_USER_MISMATCH")
        if not valid_sid(evidence.declared_sid) or evidence.declared_sid != evidence.actual_sid:
            problems.append(f"{guest}:DECLARED_ACTUAL_MISMATCH")
        for label, sid, seen in (
            ("ACTUAL", evidence.actual_sid, seen_actual),
            ("TOKEN", evidence.token_sid, seen_token),
        ):
            if valid_sid(sid):
                if sid in seen:
                    problems.append(f"{label}_SID_REUSED:{seen[sid]}:{guest}")
                else:
                    seen[sid] = guest
        if evidence.elevated is True:
            problems.append(f"{guest}:ELEVATED_TOKEN")
        elif type(evidence.elevated) is not bool:
            problems.append(f"{guest}:ELEVATION_UNPROVEN")
        if not valid_group_sids(evidence.group_sids):
            problems.append(f"{guest}:GROUP_MEMBERSHIP_UNPROVEN")
        for sid in evidence.group_sids if type(evidence.group_sids) is tuple else ():
            if sid in privileged_groups:
                problems.append(f"{guest}:PRIVILEGED_GROUP:{sid}")
                owner = seen_privileged.setdefault(sid, guest)
                if owner != guest:
                    problems.append(f"SHARED_PRIVILEGED_GROUP:{owner}:{guest}:{sid}")
        if evidence.acl_verified is not True or evidence.independently_attested is not True:
            problems.append(f"{guest}:ISOLATION_UNPROVEN")
    return tuple(problems)
