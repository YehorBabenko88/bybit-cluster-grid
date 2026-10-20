"""Offline completeness audit for independently sourced VM principal evidence.

No Windows APIs, filesystem reads, guest access, or execution authorization.
"""
from dataclasses import dataclass
from typing import Mapping, Tuple
from .sid_validation import evidence_mapping_types

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
                    or isinstance(evidence[field], bool) and field not in (
                        "effective_read", "effective_write", "effective_write_dac")
                    or isinstance(evidence[field], str) and not evidence[field].strip()
                    or isinstance(evidence[field], (tuple, list, dict, set)) and not evidence[field]
                    or field in ("effective_read", "effective_write", "effective_write_dac")
                    and type(evidence[field]) is not bool)
    # Incomplete or wrong-type observation is not completeness, much less authenticity.
    invalid = evidence_mapping_types(evidence)
    invalid_fields = []
    for problem in invalid:
        if problem.startswith("INVALID_TOKEN_GROUP_SIDS"):
            invalid_fields.append("token_group_sids")
        elif problem.startswith("INVALID_TOKEN_INTEGRITY"):
            invalid_fields.append("token_integrity")
        elif problem.startswith("INVALID_TOKEN_ELEVATION"):
            invalid_fields.append("token_elevation")
        elif problem.endswith(":INVALID_EFFECTIVE_ACCESS"):
            invalid_fields.append(problem.split(":")[0])
        elif problem.endswith(":INVALID_SID"):
            invalid_fields.append(problem.split(":")[0])
    for field in ("object_dacl_digest", "source_id", "observed_at", "evidence_digest"):
        if type(evidence.get(field)) is not str:
            invalid_fields.append(field)
    missing = tuple(field for field in REQUIRED_FIELDS if field in missing or field in invalid_fields)
    # Completeness remains purely syntactic, never READY and never authenticated.
    return CompletenessResult(not missing, missing)
