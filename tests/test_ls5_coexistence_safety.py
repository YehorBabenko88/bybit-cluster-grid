"""Pure offline coexistence and no-arbitrary-cleanup regressions."""
from dataclasses import replace
import pytest
from installer.ls5_coexistence_safety import Observation, assess

RUN = "a" * 32
OWNER = "S-1-5-21-101-202-303"


def valid():
    return Observation(
        run_id=RUN, root="C:\\GridLab\\FirstBoot\\" + RUN + "\\LS5",
        root_file_id="volume:17:file:123", root_owner_sid=OWNER,
        root_acl_verified=True, root_reparse=False, ancestor_custody=True,
        process_pid=4242, process_created_ns=123456789,
        process_owner_sid=OWNER, process_exe_sha256="b" * 64,
        process_run_id=RUN, process_parent_identity_verified=True,
        process_tree_closed=True, unknown_descendants=False,
        production_process_untouched=True, production_root_disjoint=True,
        journal_complete=True,
    )


def test_all_claims_still_cannot_authorize_physical_cleanup():
    result = assess(valid())
    assert result["status"] == "OFFLINE_MODEL_PASS"
    assert result["execute_authorized"] is False
    assert result["cleanup_authorized"] is False
    assert result["bootstrap_physical_readiness"] == "NO-GO"


@pytest.mark.parametrize("mutation,reason", [
    ({"process_pid": 0}, "PID_UNKNOWN"),
    ({"process_pid": "4242"}, "PID_UNKNOWN"),
    ({"process_created_ns": 0}, "PID_REUSE_UNVERIFIED"),
    ({"process_created_ns": "123456789"}, "PID_REUSE_UNVERIFIED"),
    ({"process_owner_sid": "S-1-5-21-1-2-3"}, "PROCESS_OWNER_MISMATCH"),
    ({"process_run_id": "c" * 32}, "PROCESS_RUN_MISMATCH"),
    ({"process_exe_sha256": "unknown"}, "EXECUTABLE_IDENTITY_UNKNOWN"),
    ({"root_file_id": ""}, "FILE_ID_UNKNOWN"),
    ({"root_acl_verified": "true"}, "ROOT_ACL_VERIFIED_UNPROVEN"),
    ({"ancestor_custody": False}, "ANCESTOR_CUSTODY_UNPROVEN"),
    ({"root_reparse": True}, "REPARSE_UNKNOWN_OR_PRESENT"),
    ({"root_reparse": "false"}, "REPARSE_UNKNOWN_OR_PRESENT"),
    ({"process_parent_identity_verified": False}, "PROCESS_PARENT_IDENTITY_VERIFIED_UNPROVEN"),
    ({"process_tree_closed": False}, "PROCESS_TREE_CLOSED_UNPROVEN"),
    ({"unknown_descendants": True}, "UNKNOWN_DESCENDANTS"),
    ({"production_process_untouched": False}, "PRODUCTION_PROCESS_UNTOUCHED_UNPROVEN"),
    ({"production_root_disjoint": False}, "PRODUCTION_ROOT_DISJOINT_UNPROVEN"),
    ({"journal_complete": False}, "JOURNAL_COMPLETE_UNPROVEN"),
    ({"cleanup_authorized": True}, "FORGED_CLEANUP_AUTHORITY"),
    ({"root": "C:\\ProgramData\\BybitClusterGrid"}, "ROOT_INVALID"),
    ({"root": "C:\\GridLab\\FirstBoot\\" + RUN + "\\LS5\\..\\PC4"}, "ROOT_INVALID"),
    ({"root": "C:\\GridLab\\FirstBoot\\" + RUN + "\\LS5:evil"}, "ROOT_INVALID"),
    ({"root": "\\\\server\\share"}, "ROOT_INVALID"),
    ({"root": "C:\\GridLab\\FirstBoot\\" + RUN + "\\LＳ5"}, "ROOT_INVALID"),
])
def test_forged_process_and_path_evidence_blocks(mutation, reason):
    result = assess(replace(valid(), **mutation))
    assert result["status"] == "BLOCKED"
    assert reason in result["reasons"]
    assert result["cleanup_authorized"] is False


def test_non_observation_is_blocked():
    assert assess({"pid": 4242})["status"] == "BLOCKED"


def test_existing_grid_and_new_grid_can_coexist_only_as_claimed_model():
    result = assess(valid())
    assert result["status"] == "OFFLINE_MODEL_PASS"
    assert result["bootstrap_physical_readiness"] == "NO-GO"

@pytest.mark.parametrize("sid", [
    "S-1-5-21-4294967296-2-3",
    "S-1-5-21-01-2-3",
    "S-1-5-21-1-2-999999999999999999999999",
    "S-1-5-21-١-2-3",
    "S-1-5-21-1-2",
])
def test_noncanonical_sid_rejected(sid):
    result = assess(replace(valid(), root_owner_sid=sid))
    assert result["status"] == "BLOCKED"
    assert "ROOT_OWNER_UNKNOWN" in result["reasons"]


def test_other_run_root_rejected():
    other = "c" * 32
    result = assess(replace(valid(), root="C:\\GridLab\\FirstBoot\\" + other + "\\LS5"))
    assert result["status"] == "BLOCKED"
    assert "ROOT_INVALID" in result["reasons"]
