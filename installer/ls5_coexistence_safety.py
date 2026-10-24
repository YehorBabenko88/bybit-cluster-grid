"""Synthetic coexistence and cleanup *refusal* model.

Never queries Windows, opens a handle, kills a process or deletes a path.
Only a native, independently reviewed controller can perform an authorized operation.
"""
from dataclasses import dataclass
import ntpath
import re

RUN = re.compile(r"[0-9a-f]{32}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
HEX = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class Observation:
    run_id: str
    root: str
    root_file_id: str
    root_owner_sid: str
    root_acl_verified: bool
    root_reparse: bool
    ancestor_custody: bool
    process_pid: int
    process_created_ns: int
    process_owner_sid: str
    process_exe_sha256: str
    process_run_id: str
    process_parent_identity_verified: bool
    process_tree_closed: bool
    unknown_descendants: bool
    production_process_untouched: bool
    production_root_disjoint: bool
    journal_complete: bool
    cleanup_authorized: bool = False


def _root(value):
    if type(value) is not str or not re.fullmatch(
        r"C:\\GridLab\\FirstBoot\\[0-9a-f]{32}\\(LS5|PC4)", value
    ):
        return None
    return ntpath.normcase(ntpath.normpath(value))


def _sid(value):
    if type(value) is not str:
        return False
    parts = value.split("-")
    if len(parts) != 8 or parts[:4] != ["S", "1", "5", "21"]:
        return False
    if any(not part.isascii() or not part.isdecimal() or
           (len(part) > 1 and part[0] == "0") for part in parts[4:]):
        return False
    return all(0 <= int(part) <= 4294967295 for part in parts[4:])


def assess(observation):
    reasons = []
    if type(observation) is not Observation:
        return {"status": "BLOCKED", "reasons": ["INVALID_OBSERVATION"],
                "execute_authorized": False, "cleanup_authorized": False,
                "bootstrap_physical_readiness": "NO-GO"}
    o = observation
    if type(o.run_id) is not str or not RUN.fullmatch(o.run_id):
        reasons.append("RUN_ID_INVALID")
    if _root(o.root) is None or (type(o.run_id) is str and
            _root(o.root) not in (
                ntpath.normcase(ntpath.join("C:", "GridLab", "FirstBoot", o.run_id, "LS5")),
                ntpath.normcase(ntpath.join("C:", "GridLab", "FirstBoot", o.run_id, "PC4")),
            )):
        reasons.append("ROOT_INVALID")
    if type(o.root_file_id) is not str or not o.root_file_id.strip():
        reasons.append("FILE_ID_UNKNOWN")
    if not _sid(o.root_owner_sid):
        reasons.append("ROOT_OWNER_UNKNOWN")
    if not _sid(o.process_owner_sid) or o.process_owner_sid != o.root_owner_sid:
        reasons.append("PROCESS_OWNER_MISMATCH")
    if type(o.process_pid) is not int or o.process_pid <= 0:
        reasons.append("PID_UNKNOWN")
    if type(o.process_created_ns) is not int or o.process_created_ns <= 0:
        reasons.append("PID_REUSE_UNVERIFIED")
    if type(o.process_exe_sha256) is not str or not SHA.fullmatch(o.process_exe_sha256):
        reasons.append("EXECUTABLE_IDENTITY_UNKNOWN")
    if type(o.process_run_id) is not str or o.process_run_id != o.run_id:
        reasons.append("PROCESS_RUN_MISMATCH")
    for field in ("root_acl_verified", "ancestor_custody",
                  "process_parent_identity_verified", "process_tree_closed",
                  "production_process_untouched", "production_root_disjoint",
                  "journal_complete"):
        if getattr(o, field) is not True:
            reasons.append(field.upper() + "_UNPROVEN")
    if o.root_reparse is not False:
        reasons.append("REPARSE_UNKNOWN_OR_PRESENT")
    if o.unknown_descendants is not False:
        reasons.append("UNKNOWN_DESCENDANTS")
    if o.cleanup_authorized is not False:
        reasons.append("FORGED_CLEANUP_AUTHORITY")
    return {
        "status": "OFFLINE_MODEL_PASS" if not reasons else "BLOCKED",
        "reasons": reasons,
        "execute_authorized": False,
        "cleanup_authorized": False,
        "bootstrap_physical_readiness": "NO-GO",
    }
