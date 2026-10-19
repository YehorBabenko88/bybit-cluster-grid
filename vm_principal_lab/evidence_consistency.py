"""Read-only evidence consistency checks, not Windows authorization decisions."""
from dataclasses import dataclass
from typing import Mapping, Tuple

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
    if len(claims) < 2:
        errors.append("INSUFFICIENT_INDEPENDENT_SOURCES")
    by_principal = {}
    for key, claim in sorted(claims.items()):
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
    for principal, group in sorted(by_principal.items()):
        if len({c.source for c in group}) != len(group):
            errors.append(f"{principal}:DUPLICATE_SOURCE")
        for field in ("observed_sid", "token_sid", "elevation", "group_sids", "acl_digest"):
            if len({getattr(c, field) for c in group}) > 1:
                errors.append(f"{principal}:{field.upper()}_CONFLICT")
    return tuple(errors)
