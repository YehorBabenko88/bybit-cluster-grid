"""Independent fail-closed PC4 readiness review. No host access or execution.

This is a checklist validator, not a physical attestor or an authorization service.
Even a complete checklist cannot issue execution permission.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = (
    "owner_signed_scope", "full_sid_identity", "account_lifecycle_approved",
    "interactive_logon_effective_allow", "interactive_logon_denies_excluded",
    "seclogon_side_effect_approved", "role_parent_dacl_owner_verified",
    "child_acl_inheritance_verified", "bootstrap_code_and_artifact_pinned",
    "credential_handling_approved", "evidence_custody_independent",
    "stop_and_partial_failure_plan", "two_independent_reviewers",
)
NETWORK = (
    "ls5_peer_identity_verified", "ssh_authorization_verified",
    "tailscale_policy_verified", "no_cross_role_write_path",
    "disconnect_failure_mode_verified",
)


def evaluate(checklist: object) -> dict:
    """Review only explicitly evidenced assertions; never authorize a run."""
    if type(checklist) is not dict or set(checklist) != {"schema", "checks"}:
        return _blocked("INVALID_CHECKLIST")
    if type(checklist["schema"]) is not int or checklist["schema"] != 1:
        return _blocked("INVALID_SCHEMA")
    checks = checklist["checks"]
    if type(checks) is not dict or set(checks) != set(REQUIRED + NETWORK):
        return _blocked("INCOMPLETE_OR_UNKNOWN_CHECKS")
    for key, value in checks.items():
        if type(value) is not dict or set(value) != {"status", "evidence_ref"}:
            return _blocked("INVALID_CHECK")
        if value["status"] not in ("VERIFIED", "UNKNOWN", "BLOCKED"):
            return _blocked("INVALID_STATUS")
        if type(value["evidence_ref"]) is not str or len(value["evidence_ref"]) > 256:
            return _blocked("INVALID_EVIDENCE_REFERENCE")
        if value["status"] == "VERIFIED" and not value["evidence_ref"].strip():
            return _blocked("UNREFERENCED_VERIFICATION")
    missing_local = [k for k in REQUIRED if checks[k]["status"] != "VERIFIED"]
    missing_network = [k for k in NETWORK if checks[k]["status"] != "VERIFIED"]
    return {
        "schema": 1,
        "local_review": "REVIEWABLE_NOT_AUTHORIZED" if not missing_local else "NO_GO",
        "pc4_ls5_review": "REVIEWABLE_NOT_AUTHORIZED" if not (missing_local or missing_network) else "NO_GO",
        "local_blockers": missing_local,
        "network_blockers": missing_network,
        "physical_attestation": False,
        "execution_authorized": False,
        "readiness_passed": False,
        "schema_2_enabled": False,
    }


def _blocked(reason: str) -> dict:
    return {
        "schema": 1, "local_review": "NO_GO", "pc4_ls5_review": "NO_GO",
        "local_blockers": [reason], "network_blockers": [reason],
        "physical_attestation": False, "execution_authorized": False,
        "readiness_passed": False, "schema_2_enabled": False,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checklist", type=Path)
    args = parser.parse_args()
    try:
        if args.checklist.stat().st_size > 65536:
            raise ValueError("OVERSIZED_CHECKLIST")
        data = json.loads(args.checklist.read_text(encoding="utf-8"),
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        result = evaluate(data)
    except (OSError, UnicodeError, ValueError, TypeError):
        result = _blocked("UNREADABLE_CHECKLIST")
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["local_review"] == "REVIEWABLE_NOT_AUTHORIZED" else 2)
