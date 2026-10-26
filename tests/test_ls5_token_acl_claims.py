"""Adversarial synthetic evidence; never reads host tokens or ACLs."""
from copy import deepcopy
import pytest
from installer.ls5_token_acl_claims import assess

SID = "S-1-5-21-101-202-303"


def sample():
    return {
        "role": "COLLECTOR", "account_enabled": True, "user_sid": SID,
        "token_sid": SID, "integrity_rid": 8192, "elevated": False,
        "impersonating": False, "administrators_enabled": False,
        "token_groups_complete": True, "token_privileges_complete": True,
        "effective_access_observed": True, "acl_owner_sid": SID,
        "acl_parent_delete_child_denied": True, "acl_write_dac_denied": True,
        "acl_write_owner_denied": True, "acl_inheritance_resolved": True,
        "acl_reparse_absent": True, "stable_process_handle": True,
        "process_creation_ns": 123456789, "process_image_sha256": "a" * 64,
        "process_parent_bound": True, "process_tree_closed": True,
        "source_loader_closed": True, "source_provenance_authenticated": True,
    }


def test_all_claims_still_not_physical_go():
    result = assess(sample())
    assert result["status"] == "OFFLINE_MODEL_PASS"
    assert result["host_verified"] is False
    assert result["effective_access_verified"] is False
    assert result["execute_authorized"] is False
    assert result["cleanup_authorized"] is False
    assert result["bootstrap_physical_readiness"] == "NO-GO"
    assert "INDEPENDENT_NATIVE_WITNESS_REQUIRED" in result["issues"]


@pytest.mark.parametrize("field,value,reason", [
    ("user_sid", "S-1-5-21-4294967296-2-3", "TOKEN_IDENTITY_UNKNOWN"),
    ("token_sid", "S-1-5-21-1-2-3", "TOKEN_IDENTITY_UNKNOWN"),
    ("user_sid", "S-1-5-21-٠-2-3", "TOKEN_IDENTITY_UNKNOWN"),
    ("account_enabled", "true", "ACCOUNT_ENABLED_UNPROVEN"),
    ("impersonating", True, "IMPERSONATION_UNKNOWN"),
    ("impersonating", "false", "IMPERSONATION_UNKNOWN"),
    ("elevated", True, "NONADMIN_BOUNDARY_UNKNOWN"),
    ("administrators_enabled", True, "NONADMIN_BOUNDARY_UNKNOWN"),
    ("token_groups_complete", False, "TOKEN_GROUPS_COMPLETE_UNPROVEN"),
    ("token_privileges_complete", "true", "TOKEN_PRIVILEGES_COMPLETE_UNPROVEN"),
    ("effective_access_observed", False, "EFFECTIVE_ACCESS_OBSERVED_UNPROVEN"),
    ("acl_parent_delete_child_denied", False, "ACL_PARENT_DELETE_CHILD_DENIED_UNPROVEN"),
    ("acl_write_dac_denied", False, "ACL_WRITE_DAC_DENIED_UNPROVEN"),
    ("acl_write_owner_denied", False, "ACL_WRITE_OWNER_DENIED_UNPROVEN"),
    ("acl_inheritance_resolved", False, "ACL_INHERITANCE_RESOLVED_UNPROVEN"),
    ("acl_reparse_absent", False, "ACL_REPARSE_ABSENT_UNPROVEN"),
    ("stable_process_handle", False, "STABLE_PROCESS_HANDLE_UNPROVEN"),
    ("process_creation_ns", 0, "PROCESS_CREATION_UNKNOWN"),
    ("process_image_sha256", "bad", "PROCESS_IMAGE_UNKNOWN"),
    ("process_parent_bound", False, "PROCESS_PARENT_BOUND_UNPROVEN"),
    ("process_tree_closed", False, "PROCESS_TREE_CLOSED_UNPROVEN"),
    ("source_loader_closed", False, "SOURCE_LOADER_CLOSED_UNPROVEN"),
    ("source_provenance_authenticated", False, "SOURCE_PROVENANCE_AUTHENTICATED_UNPROVEN"),
])
def test_untrusted_observation_is_blocked(field, value, reason):
    data = sample()
    data[field] = value
    result = assess(data)
    assert result["status"] == "BLOCKED"
    assert reason in result["issues"]
    assert not result["execute_authorized"]


def test_unknown_and_missing_fields_fail_closed():
    for mutation in ("remove", "add"):
        data = sample()
        if mutation == "remove":
            del data["token_sid"]
        else:
            data["fake_pass"] = True
        assert assess(data)["status"] == "BLOCKED"


def test_storage_disabled_account_blocks():
    data = sample()
    data["role"] = "STORAGE"
    data["account_enabled"] = False
    assert assess(data)["status"] == "BLOCKED"
