"""Offline completeness audit for independently sourced VM principal evidence.

No Windows APIs, filesystem reads, guest access, or execution authorization.
"""
from dataclasses import dataclass
from typing import Mapping, Tuple

REQUIRED_FIELDS = (
    "declared_sid", "actual_sid", "token_user_sid", "token_group_sids",
    "token_elevation", "token_integrity", "object_owner_sid",
    "object_dacl_digest", "effective_read", "effective_write",
    "effective_write_dac", "source_id", "observed_at", "evidence_digest",
)

@dataclass(frozen=True)
class CompletenessResult:
    complete: bool
    missing: Tuple[str, ...]
    status: str = "BLOCKED_UNPROVEN"
    readiness_passed: bool = False
    execution_authorized: bool = False

def audit_evidence_completeness(evidence: Mapping[str, object]) -> CompletenessResult:
    if not isinstance(evidence, Mapping):
        return CompletenessResult(False, REQUIRED_FIELDS)
    missing = tuple(field for field in REQUIRED_FIELDS
                    if field not in evidence or evidence[field] is None
                    or (isinstance(evidence[field], str) and not evidence[field].strip()))
    # Presence is not authenticity. Never promote to READY even when all fields exist.
    return CompletenessResult(not missing, missing)
