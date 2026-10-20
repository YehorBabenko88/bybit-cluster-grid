"""Twelve non-executable negative-case specifications for independent VM attestation.

These are model-only test vectors, not evidence of guest execution.
"""
from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class NegativeCase:
    case_id: str
    stimulus: str
    required_evidence: Tuple[str, ...]
    expected: str = "NOT_RUN"

NEGATIVE_CASES = (
    NegativeCase("VM-NEG-01", "declared SID without actual SID", ("actual_sid",)),
    NegativeCase("VM-NEG-02", "shared actual SID across guests", ("actual_sid_per_guest",)),
    NegativeCase("VM-NEG-03", "token user SID mismatch", ("token_user_sid",)),
    NegativeCase("VM-NEG-04", "missing elevation evidence", ("token_elevation",)),
    NegativeCase("VM-NEG-05", "unexpected elevated token", ("token_elevation", "token_integrity")),
    NegativeCase("VM-NEG-06", "missing group membership evidence", ("token_group_sids",)),
    NegativeCase("VM-NEG-07", "shared privileged group", ("token_group_sids", "group_attributes")),
    NegativeCase("VM-NEG-08", "ACL allows cross-guest read", ("object_dacl", "effective_access")),
    NegativeCase("VM-NEG-09", "ACL allows cross-guest write", ("object_dacl", "effective_access")),
    NegativeCase("VM-NEG-10", "owner can rewrite isolation ACL", ("owner_sid", "write_dac_access")),
    NegativeCase("VM-NEG-11", "evidence lacks independent attestation", ("attestation_provenance",)),
    NegativeCase("VM-NEG-12", "hostile administrator interference", ("hostile_admin_stop",)),
)

def validate_protocol() -> bool:
    ids = [case.case_id for case in NEGATIVE_CASES]
    return (len(ids) == len(set(ids)) == 12
            and ids == [f"VM-NEG-{i:02d}" for i in range(1, 13)]
            and all(case.expected == "NOT_RUN" and case.required_evidence
                    for case in NEGATIVE_CASES))
