"""Read-only evidence consistency checks, not Windows authorization decisions."""
from dataclasses import dataclass
from typing import Mapping, Tuple
from .sid_validation import valid_sid, valid_group_sids

@dataclass(frozen=True)
class EvidenceClaim:
    principal: str
    source: str
    observed_sid: str
    token_sid: str
    elevation: str
    group_sids: Tuple[str, ...]
    acl_digest: str

def detect_evidence_conflicts(claims: Mapping[str, EvidenceClaim]) -> Tuple[str, ...]:
    """Detect disagreement and missing provenance; never infer execution permission."""
    errors = []
    if not isinstance(claims, Mapping):
        return ("INVALID_CLAIMS",)
    if len(claims) < 2:
        errors.append("INSUFFICIENT_INDEPENDENT_SOURCES")
    by_principal = {}
    source_owners = {}
    sid_owners = {}
    token_owners = {}
    for key, claim in sorted(claims.items(), key=lambda item: str(item[0])):
        if type(key) is not str or not key or not isinstance(claim, EvidenceClaim):
            errors.append(f"{key}:INVALID_CLAIM")
            continue
        if type(claim.principal) is not str or not claim.principal or type(claim.source) is not str or not claim.source:
            errors.append(f"{key}:INVALID_PROVENANCE")
            errors.append(f"{key}:MISSING_PROVENANCE")
            if not isinstance(claim.acl_digest, str) or not claim.acl_digest:
                errors.append(f"{key}:ACL_EVIDENCE_MISSING")
            if claim.elevation not in ("limited", "elevated"):
                errors.append(f"{key}:ELEVATION_UNKNOWN")
            continue
        if not valid_sid(claim.observed_sid) or not valid_sid(claim.token_sid):
            errors.append(f"{key}:INVALID_SID")
            continue
        if not valid_group_sids(claim.group_sids):
            errors.append(f"{key}:INVALID_GROUP_SIDS")
            continue
        if type(claim.elevation) is not str or claim.elevation not in ("limited", "elevated"):
            errors.append(f"{key}:INVALID_ELEVATION")
            continue
        if claim.elevation == "elevated":
            errors.append(f"{key}:ELEVATED_TOKEN_UNSAFE")
        if type(claim.acl_digest) is not str or not claim.acl_digest:
            errors.append(f"{key}:ACL_EVIDENCE_MISSING")
            continue
        if not claim.source or not claim.principal:
            errors.append(f"{key}:MISSING_PROVENANCE")
        if not claim.observed_sid or not claim.token_sid:
            errors.append(f"{key}:MISSING_SID")
        elif claim.observed_sid != claim.token_sid:
            errors.append(f"{key}:SID_TOKEN_CONFLICT")
        if not claim.acl_digest:
            errors.append(f"{key}:ACL_EVIDENCE_MISSING")
        if claim.elevation not in ("elevated", "limited"):
            errors.append(f"{key}:ELEVATION_UNKNOWN")
        by_principal.setdefault(claim.principal, []).append(claim)
        if claim.source and claim.principal:
            owner = source_owners.setdefault(claim.source, claim.principal)
            if owner != claim.principal:
                errors.append(f"{key}:SOURCE_REUSED_ACROSS_PRINCIPALS")
        if claim.observed_sid and claim.principal:
            owner = sid_owners.setdefault(claim.observed_sid, claim.principal)
            if owner != claim.principal:
                errors.append(f"{key}:OBSERVED_SID_REUSED_ACROSS_PRINCIPALS")
        if claim.token_sid and claim.principal:
            owner = token_owners.setdefault(claim.token_sid, claim.principal)
            if owner != claim.principal:
                errors.append(f"{key}:TOKEN_SID_REUSED_ACROSS_PRINCIPALS")
    for principal, group in sorted(by_principal.items()):
        if len({c.source for c in group if c.source}) < 2:
            errors.append(f"{principal}:INSUFFICIENT_INDEPENDENT_SOURCES")
        if len({c.source for c in group}) != len(group):
            errors.append(f"{principal}:DUPLICATE_SOURCE")
        for field in ("observed_sid", "token_sid", "elevation", "group_sids", "acl_digest"):
            if len({getattr(c, field) for c in group}) > 1:
                errors.append(f"{principal}:{field.upper()}_CONFLICT")
    return tuple(errors)
