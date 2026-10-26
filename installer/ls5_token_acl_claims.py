"""Offline validation of claimed Windows token/ACL/handle observations.

This model never calls Windows APIs. In particular it cannot perform AccessCheck,
verify a token handle or establish physical authorization.
"""
import re

SID = re.compile(r"S-1-5-21-(?:0|[1-9][0-9]*)-(?:0|[1-9][0-9]*)-(?:0|[1-9][0-9]*)\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED = {
    "role", "account_enabled", "user_sid", "token_sid", "integrity_rid",
    "elevated", "impersonating", "administrators_enabled", "token_groups_complete",
    "token_privileges_complete", "effective_access_observed", "acl_owner_sid",
    "acl_parent_delete_child_denied", "acl_write_dac_denied",
    "acl_write_owner_denied", "acl_inheritance_resolved", "acl_reparse_absent",
    "stable_process_handle", "process_creation_ns", "process_image_sha256",
    "process_parent_bound", "process_tree_closed", "source_loader_closed",
    "source_provenance_authenticated",
}


def _sid(value):
    if type(value) is not str or not SID.fullmatch(value):
        return False
    return all(int(p) <= 4294967295 for p in value.split("-")[4:])


def assess(observation):
    result = {
        "status": "BLOCKED", "host_verified": False,
        "effective_access_verified": False, "execute_authorized": False,
        "cleanup_authorized": False, "bootstrap_physical_readiness": "NO-GO",
        "issues": [],
    }
    issues = result["issues"]
    if type(observation) is not dict or set(observation) != REQUIRED:
        issues.append("MISSING_OR_UNKNOWN_FIELDS")
        return result
    o = observation
    if o["role"] not in ("COLLECTOR", "STORAGE", "CONTROL", "WORKER"):
        issues.append("ROLE_UNKNOWN")
    if not _sid(o["user_sid"]) or not _sid(o["token_sid"]) or o["user_sid"] != o["token_sid"]:
        issues.append("TOKEN_IDENTITY_UNKNOWN")
    if not _sid(o["acl_owner_sid"]):
        issues.append("ACL_OWNER_UNKNOWN")
    if type(o["integrity_rid"]) is not int or not 0 <= o["integrity_rid"] <= 16384:
        issues.append("INTEGRITY_UNKNOWN")
    if o["role"] in ("COLLECTOR", "STORAGE", "WORKER") and (
        o["elevated"] is not False or o["administrators_enabled"] is not False
    ):
        issues.append("NONADMIN_BOUNDARY_UNKNOWN")
    if o["role"] in ("COLLECTOR", "STORAGE", "WORKER") and (
        type(o["integrity_rid"]) is not int or o["integrity_rid"] > 8192
    ):
        issues.append("WORKER_INTEGRITY_TOO_HIGH")
    if o["impersonating"] is not False:
        issues.append("IMPERSONATION_UNKNOWN")
    if type(o["process_creation_ns"]) is not int or o["process_creation_ns"] <= 0:
        issues.append("PROCESS_CREATION_UNKNOWN")
    if type(o["process_image_sha256"]) is not str or not SHA.fullmatch(o["process_image_sha256"]):
        issues.append("PROCESS_IMAGE_UNKNOWN")
    for field in (
        "account_enabled", "token_groups_complete", "token_privileges_complete",
        "effective_access_observed", "acl_parent_delete_child_denied",
        "acl_write_dac_denied", "acl_write_owner_denied",
        "acl_inheritance_resolved", "acl_reparse_absent", "stable_process_handle",
        "process_parent_bound", "process_tree_closed", "source_loader_closed",
        "source_provenance_authenticated",
    ):
        if o[field] is not True:
            issues.append(field.upper() + "_UNPROVEN")
    # Even all self-reported claims cannot authenticate AccessCheck or handles.
    if not issues:
        result["status"] = "OFFLINE_MODEL_PASS"
        issues.append("INDEPENDENT_NATIVE_WITNESS_REQUIRED")
    return result
