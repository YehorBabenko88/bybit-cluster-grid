"""Strict, offline-only validation of untrusted Windows SID and evidence shapes.

Syntax is never proof of guest identity, provenance, ACL effectiveness or authority.
"""
import re
from typing import Mapping

_SID_RE = re.compile(r"S-1-(0|[1-9][0-9]*)(?:-(0|[1-9][0-9]*)){1,15}\\Z", re.ASCII)
_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)\\Z", re.ASCII)
MAX_AUTHORITY = (1 << 48) - 1
MAX_SUBAUTHORITY = (1 << 32) - 1
MAX_SID_STRING_LENGTH = 184  # max canonical decimal SID text: revision + 48-bit authority + 15 DWORDs


def valid_sid(value: object) -> bool:
    """Validate canonical decimal textual SID within binary Windows SID limits."""
    if type(value) is not str or len(value) > MAX_SID_STRING_LENGTH:
        return False
    if _SID_RE.fullmatch(value) is None:
        return False
    parts = value.split("-")
    if not (4 <= len(parts) <= 18):
        return False
    # Revision is fixed at 1. Exactly 1..15 binary DWORD subauthorities.
    return (int(parts[2]) <= MAX_AUTHORITY and
            all(int(part) <= MAX_SUBAUTHORITY for part in parts[3:]))


def valid_integrity_sid(value: object) -> bool:
    """Integrity SID: mandatory-label authority 16 and exactly one RID."""
    return valid_sid(value) and value.count("-") == 3 and value.startswith("S-1-16-")


def valid_group_sids(value: object) -> bool:
    """Require an immutable tuple of unique canonical group SIDs."""
    return type(value) is tuple and bool(value) and all(valid_sid(s) for s in value) and len(value) == len(set(value))


def principal_shape_issues(evidence: object) -> tuple[str, ...]:
    """Validate PrincipalEvidence fields, without trusting dataclass annotations."""
    if evidence is None:
        return ("INVALID_EVIDENCE",)
    errors = []
    for name in ("declared_sid", "actual_sid", "token_sid"):
        value = getattr(evidence, name, None)
        if not valid_sid(value):
            errors.append(f"{name}:INVALID_SID")
    if not valid_group_sids(getattr(evidence, "group_sids", None)):
        errors.append("group_sids:INVALID_GROUP_SIDS")
    for name in ("elevated", "acl_verified", "independently_attested"):
        if type(getattr(evidence, name, None)) is not bool:
            errors.append(f"{name}:INVALID_BOOLEAN")
    return tuple(errors)


def evidence_mapping_types(evidence: object) -> tuple[str, ...]:
    """Validate fields in an extended ACL/token observation mapping."""
    if not isinstance(evidence, Mapping):
        return ("INVALID_EVIDENCE",)
    errors = []
    for name in ("declared_sid", "actual_sid", "token_user_sid", "object_owner_sid"):
        if not valid_sid(evidence.get(name)):
            errors.append(f"{name}:INVALID_SID")
    if not valid_group_sids(evidence.get("token_group_sids")):
        errors.append("INVALID_TOKEN_GROUP_SIDS")
    if not valid_integrity_sid(evidence.get("token_integrity")):
        errors.append("INVALID_TOKEN_INTEGRITY")
    if type(evidence.get("token_elevation")) is not str or evidence.get("token_elevation") not in ("limited", "elevated"):
        errors.append("INVALID_TOKEN_ELEVATION")
    for name in ("effective_read", "effective_write", "effective_write_dac"):
        if type(evidence.get(name)) is not bool:
            errors.append(f"{name}:INVALID_EFFECTIVE_ACCESS")
    return tuple(errors)
