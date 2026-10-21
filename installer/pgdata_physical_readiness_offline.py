"""Fail-closed PostgreSQL physical-readiness planning gate.

Pure data evaluation. No filesystem, PostgreSQL, Windows, service or network calls.
Evidence claims are untrusted; even fully populated inputs cannot authorize I/O.
"""
from __future__ import annotations

import re

CONTRACT = "PGDATA_PHYSICAL_READINESS_OFFLINE_V1"
FIELDS = (
    "layout_decision", "native_path_inventory", "existing_cluster_exclusion",
    "full_sid_token_acl_review", "service_identity_review",
    "storage_capacity_review", "backup_wal_retention_review",
    "off_host_copy_review", "isolated_restore_review",
    "integrity_reconciliation_review", "migration_rehearsal_review",
    "independent_human_reviews", "physical_authorization",
)
FLAGS = (
    "execution_authorized", "readiness_passed", "physical_ready",
    "ownership_verified", "schema2_enabled",
)
ALLOWED = {"UNKNOWN", "BLOCKED", "EVIDENCE_PROPOSED"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def evaluate(packet):
    """Inspect a closed *offline* planning packet, never grant readiness."""
    errors = []
    valid = type(packet) is dict and set(packet) == {
        "contract", "source_commit", "evidence", "requested_action"
    }
    if not valid:
        errors.append("PACKET_SCHEMA_INVALID")
    else:
        if packet["contract"] != CONTRACT:
            errors.append("CONTRACT_INVALID")
        if type(packet["source_commit"]) is not str or not re.fullmatch(
            r"[0-9a-f]{40}", packet["source_commit"]
        ):
            errors.append("SOURCE_COMMIT_INVALID")
        if packet["requested_action"] != "OFFLINE_REVIEW_ONLY":
            errors.append("ACTION_NOT_AUTHORIZED")
        evidence = packet["evidence"]
        if type(evidence) is not dict or set(evidence) != set(FIELDS):
            errors.append("EVIDENCE_SCHEMA_INVALID")
        else:
            for field in FIELDS:
                item = evidence[field]
                if type(item) is not dict or set(item) != {"state", "sha256"}:
                    errors.append("EVIDENCE_ITEM_INVALID:" + field)
                    continue
                if type(item["state"]) is not str or item["state"] not in ALLOWED:
                    errors.append("EVIDENCE_STATE_INVALID:" + field)
                digest = item["sha256"]
                if digest is not None and (
                    type(digest) is not str or SHA256.fullmatch(digest) is None
                    or digest == "0" * 64
                ):
                    errors.append("EVIDENCE_DIGEST_INVALID:" + field)
                if item["state"] == "EVIDENCE_PROPOSED" and digest is None:
                    errors.append("EVIDENCE_DIGEST_MISSING:" + field)
    blockers = [
        "PGDATA_LAYOUT_MAPPING_UNRESOLVED",
        "PHYSICAL_OWNERSHIP_UNVERIFIED",
        "SCHEMA1_ADAPTER_MAPPING_BLOCKED",
        "EXISTING_CLUSTER_EXCLUSION_UNVERIFIED",
        "BACKUP_RESTORE_NOT_PROVEN",
        "INDEPENDENT_REVIEWS_REQUIRED",
        "PHYSICAL_AUTHORIZATION_ABSENT",
        "NATIVE_EVIDENCE_NOT_AUTHENTICATED",
    ]
    return {
        "status": "BLOCKED",
        "metadata_valid": not errors,
        "errors": errors,
        "blockers": blockers,
        "guest_vm_cases": "12 NOT_RUN",
        "pc4_sid_acl_cases": "10 NOT_RUN",
        "scope": "OFFLINE_REVIEW_ONLY",
        **{key: False for key in FLAGS},
    }
