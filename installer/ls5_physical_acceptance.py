"""Independent metadata-only acceptance gate for LS5 -> PC4; never authorizes Execute."""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET

HEAD = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
STAGES = ("ls5_readonly", "acl_remediation", "trusted_bootstrap", "postgres_readiness",
          "network_preflight", "coordinator_start", "pc4_provisioning",
          "custody_verification", "collect_local", "pc4_sid_acl",
          "limited_pilot", "rollback")
CASES = tuple(f"{role}_{case}" for role in ("collector", "storage") for case in
              ("token", "own_write", "own_read", "foreign_read_denied", "foreign_write_denied"))
FORBIDDEN = frozenset(("schema2", "schema2_enabled", "schema_2_enabled",
                       "execution_authorized", "cleanup_authorized",
                       "deployment_authorized", "physical_ready", "durable_antirollback_verified"))


class AcceptanceBlocked(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise AcceptanceBlocked("ACCEPTANCE_" + reason)


def pairs(items):
    obj = {}
    for k, v in items:
        require(k not in obj, "DUPLICATE_JSON_KEY")
        obj[k] = v
    return obj


def no_constants(value):
    raise AcceptanceBlocked("ACCEPTANCE_NONFINITE_JSON")


def strict_json(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 4_000_000, "JSON_BYTES")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=no_constants)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise AcceptanceBlocked("ACCEPTANCE_INVALID_JSON") from None


def scan(obj, depth=0):
    require(depth <= 32, "NESTING")
    if type(obj) is dict:
        for k, v in obj.items():
            require(type(k) is str, "KEY_TYPE")
            if k in FORBIDDEN:
                require(v is False, "AUTHORITY_PROMOTION")
            scan(v, depth + 1)
    elif type(obj) is list:
        for item in obj:
            scan(item, depth + 1)


def validate_metadata(raw, *, expected_head):
    """Untrusted producer receipt; returns BLOCKED regardless of its synthetic success."""
    require(type(expected_head) is str and HEAD.fullmatch(expected_head) is not None, "EXPECTED_HEAD")
    x = strict_json(raw)
    require(type(x) is dict and set(x) == {
        "schema", "head", "stage", "source", "status", "assurance", "cases", "metadata"
    }, "RECEIPT_SCHEMA")
    require(type(x["schema"]) is int and x["schema"] == 1, "SCHEMA_VERSION")
    require(type(x["head"]) is str and x["head"] == expected_head, "HEAD_MISMATCH")
    require(type(x["stage"]) is str and x["stage"] in STAGES, "STAGE")
    require(type(x["source"]) is str and bool(x["source"]) and len(x["source"]) <= 120, "SOURCE")
    require(x["status"] == "BLOCKED" and x["assurance"] in
            ("SYNTHETIC_PASS", "HOST_READONLY_PASS", "BLOCKED_UNPROVEN"), "CLAIMED_PHYSICAL_PASS")
    require(type(x["metadata"]) is dict and type(x["cases"]) is list, "RECEIPT_TYPES")
    scan(x)
    if x["stage"] == "pc4_sid_acl":
        require(len(x["cases"]) == len(CASES), "CASE_COUNT")
        for row, name in zip(x["cases"], CASES):
            require(type(row) is dict and set(row) == {"name", "status", "assurance"}, "CASE_SCHEMA")
            require(row["name"] == name and row["status"] == "NOT_RUN" and
                    row["assurance"] == "BLOCKED_UNPROVEN", "CASE_PROMOTION")
    else:
        require(not x["cases"], "UNEXPECTED_CASES")
    return {"status": "BLOCKED", "authority": "NONE", "physical_pass": False,
            "deployment_go": False, "schema2": False,
            "pc4_cases_not_run": 10 if x["stage"] == "pc4_sid_acl" else None}


def verify_artifacts(*, head, inventory, junit, jsonl, index):
    """Verify exact inventory, hashes and offline JUnit/JSONL; not evidence provenance."""
    require(type(head) is str and HEAD.fullmatch(head) is not None, "HEAD")
    require(type(inventory) is list and inventory and
            all(type(x) is str and x and len(x) <= 256 for x in inventory), "INVENTORY")
    require(len(set(inventory)) == len(inventory), "INVENTORY_DUPLICATE")
    hashes = strict_json(index)
    require(type(hashes) is dict and set(hashes) == {"head", "files"} and
            hashes["head"] == head and type(hashes["files"]) is dict and
            set(hashes["files"]) == {"results.xml", "events.jsonl"}, "INDEX")
    for name, raw in (("results.xml", junit), ("events.jsonl", jsonl)):
        h = hashes["files"][name]
        require(type(raw) is bytes and type(h) is str and SHA.fullmatch(h) is not None
                and hashlib.sha256(raw).hexdigest() == h, "DIGEST")
    require(b"<!DOCTYPE" not in junit.upper() and b"<!ENTITY" not in junit.upper()
            and len(junit) <= 4_000_000, "XML_UNSAFE")
    try:
        root = ET.fromstring(junit)
    except (ET.ParseError, ValueError):
        raise AcceptanceBlocked("ACCEPTANCE_XML_INVALID") from None
    require(root.tag == "testsuite" and root.attrib.get("head") == head, "JUNIT_HEAD")
    require(set(root.attrib) == {"head", "tests", "failures", "errors", "skipped"}, "JUNIT_ATTRIBUTES")
    rows = list(root)
    require(len(rows) == len(inventory) and all(row.tag == "testcase" for row in rows), "JUNIT_COUNT")
    require([row.attrib.get("name") for row in rows] == inventory, "JUNIT_INVENTORY")
    require((root.text or "").strip() == "" and
            all((row.text or "").strip() == "" and (row.tail or "").strip() == ""
                for row in rows), "JUNIT_HIDDEN_TEXT")
    require(all(len(row) == 0 and set(row.attrib) == {"name"} for row in rows), "JUNIT_UNEXPECTED_OUTCOME")
    for key, expected in (("tests", len(rows)), ("failures", 0), ("errors", 0), ("skipped", 0)):
        value = root.attrib.get(key)
        require(type(value) is str and value.isdecimal() and int(value) == expected, "JUNIT_COUNTERS")
    require(type(jsonl) is bytes and jsonl.endswith(b"\n") and b"\r" not in jsonl, "JSONL_FORMAT")
    lines = jsonl.splitlines()
    require(len(lines) == len(inventory), "JSONL_COUNT")
    for line, name in zip(lines, inventory):
        event = strict_json(line)
        require(type(event) is dict and set(event) == {"head", "name", "status", "assurance"}
                and event["head"] == head and event["name"] == name and
                event["status"] == "PASS" and event["assurance"] == "SYNTHETIC_PASS",
                "JSONL_INVENTORY")
        scan(event)
    return {"status": "SYNTHETIC_PASS", "physical_pass": False, "deployment_go": False,
            "provenance_verified": False, "artifacts_consistent": True}


def decide(stage_statuses):
    require(type(stage_statuses) is dict and set(stage_statuses) == set(STAGES), "MATRIX")
    require(all(type(v) is str and v in
                ("SYNTHETIC_PASS", "HOST_READONLY_PASS", "PHYSICAL_PASS",
                 "FAIL", "BLOCKED", "NOT_RUN", "UNKNOWN")
                for v in stage_statuses.values()), "STATUS")
    return {"status": "FAIL" if "FAIL" in stage_statuses.values() else "BLOCKED",
            "physical_ready": False, "deployment_go": False,
            "reason": "NO_INDEPENDENT_PHYSICAL_AUTHORITY"}


REQUIRED_WORKFLOWS = frozenset((
    "integration-evidence-audit", "physical-deployment-harness",
    "ls5-acl-remediation", "commissioning-manifest", "composed-safety-gate",
    "isolated-postgres-offline", "preflight", "windows-commissioning",
    "windows-bundle", "ls5-physical-acceptance-offline",
))


def audit_workflow_runs(runs, *, expected_head):
    """Check workflow conclusions at exact HEAD; never confer physical authority.

    A green workflow conclusion is not proof that artifacts were downloaded,
    independently rehashed, or that any host was tested.
    """
    require(type(expected_head) is str and HEAD.fullmatch(expected_head) is not None,
            "EXPECTED_HEAD")
    require(type(runs) is list, "WORKFLOWS_TYPE")
    seen = {}
    for item in runs:
        require(type(item) is dict and set(item) == {
            "name", "head", "run_id", "attempt", "status", "conclusion"
        }, "WORKFLOW_SCHEMA")
        name, head = item["name"], item["head"]
        require(type(name) is str and 0 < len(name) <= 120, "WORKFLOW_NAME")
        require(type(head) is str and head == expected_head, "WORKFLOW_HEAD")
        require(type(item["run_id"]) is int and item["run_id"] > 0
                and type(item["attempt"]) is int and item["attempt"] > 0,
                "WORKFLOW_ID")
        require(type(item["status"]) is str and item["status"] in
                ("pending", "waiting", "requested", "queued", "in_progress", "completed"), "WORKFLOW_STATUS")
        require(item["conclusion"] in (None, "success", "failure", "cancelled",
                                       "skipped", "timed_out", "action_required",
                                       "neutral", "startup_failure"), "WORKFLOW_CONCLUSION")
        require((item["status"] == "completed") == (item["conclusion"] is not None),
                "WORKFLOW_COMPLETION")
        require(name not in seen, "WORKFLOW_DUPLICATE")
        seen[name] = item
    missing = sorted(REQUIRED_WORKFLOWS - set(seen))
    bad = sorted(name for name in REQUIRED_WORKFLOWS & set(seen)
                 if seen[name]["status"] != "completed"
                 or seen[name]["conclusion"] != "success")
    skipped = sorted(name for name, item in seen.items()
                     if item["conclusion"] == "skipped")
    return {"status": "BLOCKED", "missing_required": missing,
            "not_successful_required": bad, "skipped_workflows": skipped,
            "offline_ci_complete": not missing and not bad,
            "artifacts_independently_verified": False,
            "physical_pass": False, "deployment_go": False}


def audit_evidence_chain(chain, *, expected_head):
    """Cross-check producer/custody IDs across CI records, never authenticate them."""
    require(type(expected_head) is str and HEAD.fullmatch(expected_head) is not None, "EXPECTED_HEAD")
    require(type(chain) is dict and set(chain) == {
        "head", "run_id", "attempt", "artifact_id", "zip_sha256",
        "manifest_head", "junit_head", "jsonl_head",
        "manifest_run_id", "junit_run_id", "jsonl_run_id",
        "manifest_attempt", "junit_attempt", "jsonl_attempt",
        "custody", "source"
    }, "CHAIN_SCHEMA")
    require(all(type(chain[k]) is str and chain[k] == expected_head for k in
                ("head", "manifest_head", "junit_head", "jsonl_head")), "CHAIN_HEAD")
    require(type(chain["run_id"]) is int and chain["run_id"] > 0 and
            type(chain["attempt"]) is int and chain["attempt"] > 0 and
            type(chain["artifact_id"]) is int and chain["artifact_id"] > 0,
            "CHAIN_ID")
    require(all(type(chain[k]) is int and chain[k] == chain["run_id"] for k in
                ("manifest_run_id", "junit_run_id", "jsonl_run_id")), "CHAIN_RUN")
    require(all(type(chain[k]) is int and chain[k] == chain["attempt"] for k in
                ("manifest_attempt", "junit_attempt", "jsonl_attempt")), "CHAIN_ATTEMPT")
    require(type(chain["zip_sha256"]) is str and
            SHA.fullmatch(chain["zip_sha256"]) is not None, "CHAIN_ZIP_SHA")
    require(chain["custody"] == "UNVERIFIED" and
            chain["source"] == "GITHUB_HOSTED_SYNTHETIC", "CHAIN_AUTHORITY")
    return {"status": "BLOCKED", "internal_identity_consistent": True,
            "zip_bytes_independently_verified": False,
            "custody_authenticated": False, "physical_pass": False,
            "deployment_go": False}


def audit_gate_dependencies(gates):
    """No stage can inherit authorization from another; only report readiness gaps."""
    order = (
        ("ls5_readonly", ()),
        ("acl_remediation", ("ls5_readonly",)),
        ("trusted_bootstrap", ("acl_remediation",)),
        ("postgres_readiness", ("trusted_bootstrap",)),
        ("network_preflight", ("trusted_bootstrap",)),
        ("coordinator_start", ("postgres_readiness", "network_preflight")),
        ("pc4_provisioning", ("coordinator_start",)),
        ("custody_verification", ("pc4_provisioning",)),
        ("collect_local", ("custody_verification",)),
        ("pc4_sid_acl", ("collect_local",)),
        ("limited_pilot", ("pc4_sid_acl",)),
        ("rollback", ("limited_pilot",)),
    )
    require(type(gates) is dict and set(gates) == {name for name, _ in order}, "GATE_SET")
    allowed = {"NOT_RUN", "BLOCKED", "FAIL", "SYNTHETIC_PASS",
               "HOST_READONLY_PASS", "PHYSICAL_PASS"}
    require(all(type(v) is str and v in allowed for v in gates.values()), "GATE_STATUS")
    missing = {}
    for stage, deps in order:
        missing[stage] = [d for d in deps if gates[d] != "PHYSICAL_PASS"]
    return {"status": "FAIL" if "FAIL" in gates.values() else "BLOCKED",
            "dependencies_unproven": missing, "execute_authorized": False,
            "cleanup_authorized": False, "deployment_go": False}


def audit_ci_matrix(jobs, *, expected_head):
    """Require four independent OS/Python cells and explicit tests, not just a green workflow."""
    require(type(expected_head) is str and HEAD.fullmatch(expected_head) is not None, "MATRIX_HEAD")
    require(type(jobs) is list, "MATRIX_TYPE")
    expected = {(os_name, version) for os_name in ("ubuntu", "windows")
                for version in ("3.11", "3.12")}
    seen = {}
    for item in jobs:
        require(type(item) is dict and set(item) == {
            "head", "os", "python", "job_id", "conclusion",
            "tests", "failures", "errors", "skipped", "artifact_sha256"
        }, "MATRIX_SCHEMA")
        require(type(item["head"]) is str and item["head"] == expected_head, "MATRIX_WRONG_HEAD")
        cell = (item["os"], item["python"])
        require(all(type(v) is str for v in cell) and cell in expected, "MATRIX_CELL")
        require(cell not in seen, "MATRIX_DUPLICATE_CELL")
        require(type(item["job_id"]) is int and item["job_id"] > 0, "MATRIX_JOB")
        require(item["conclusion"] in ("success", "failure", "cancelled", "skipped",
                                       "timed_out", "neutral", None), "MATRIX_CONCLUSION")
        for key in ("tests", "failures", "errors", "skipped"):
            require(type(item[key]) is int and item[key] >= 0, "MATRIX_COUNT")
        require(type(item["artifact_sha256"]) is str and
                SHA.fullmatch(item["artifact_sha256"]) is not None, "MATRIX_SHA")
        seen[cell] = item
    missing = sorted(expected - set(seen))
    bad = sorted(cell for cell, item in seen.items()
                 if item["conclusion"] != "success" or item["tests"] < 1
                 or any(item[k] for k in ("failures", "errors", "skipped")))
    return {"status": "BLOCKED", "missing_cells": missing,
            "unaccepted_cells": bad, "synthetic_matrix_complete": not missing and not bad,
            "independent_artifact_bytes_verified": False,
            "physical_pass": False, "deployment_go": False}


INTEGRATION_PRS = (238, 239, 240, 241, 242)


def audit_cross_pr_gates(entries, *, expected_base, expected_heads=None):
    """Independent G0/G1 composition; never treats disjoint files as tested integration."""
    require(type(expected_base) is str and HEAD.fullmatch(expected_base) is not None,
            "CROSS_BASE")
    require(type(entries) is list, "CROSS_ENTRIES")
    if expected_heads is not None:
        require(type(expected_heads) is dict and set(expected_heads) == set(INTEGRATION_PRS)
                and all(type(k) is int and type(v) is str and HEAD.fullmatch(v)
                        for k, v in expected_heads.items()), "CROSS_PINNED_HEADS")
    seen = {}
    for item in entries:
        require(type(item) is dict and set(item) == {
            "pr", "base", "head", "draft", "workflow_conclusion",
            "artifact_verified", "changed_files", "contract_review"
        }, "CROSS_SCHEMA")
        pr = item["pr"]
        require(type(pr) is int and pr in INTEGRATION_PRS and pr not in seen, "CROSS_PR")
        require(type(item["base"]) is str and item["base"] == expected_base,
                "CROSS_BASE_MISMATCH")
        require(type(item["head"]) is str and HEAD.fullmatch(item["head"]) is not None,
                "CROSS_HEAD")
        if expected_heads is not None:
            require(item["head"] == expected_heads[pr], "CROSS_HEAD_MISMATCH")
        require(type(item["draft"]) is bool and item["draft"], "CROSS_DRAFT")
        require(item["workflow_conclusion"] in ("success", "failure", "queued",
                "pending", "in_progress", "skipped", "cancelled", "unknown"),
                "CROSS_WORKFLOW")
        require(type(item["artifact_verified"]) is bool and
                type(item["contract_review"]) is bool, "CROSS_EVIDENCE_TYPE")
        files = item["changed_files"]
        require(type(files) is list and all(type(p) is str and p and
                len(p) <= 512 and not p.startswith("/") and
                ".." not in p.split("/") and "\\\\" not in p for p in files),
                "CROSS_PATH")
        require(len(set(files)) == len(files), "CROSS_DUPLICATE_FILE")
        seen[pr] = item
    missing = sorted(set(INTEGRATION_PRS) - set(seen))
    g0 = sorted(pr for pr, item in seen.items()
                if item["workflow_conclusion"] != "success"
                or not item["artifact_verified"])
    g1 = sorted(pr for pr, item in seen.items() if not item["contract_review"])
    ownership = {}
    for pr, item in seen.items():
        for path in item["changed_files"]:
            ownership.setdefault(path, []).append(pr)
    overlaps = {path: sorted(owners) for path, owners in ownership.items()
                if len(owners) > 1}
    return {"status": "BLOCKED", "missing_prs": missing,
            "g0_unverified_prs": g0, "g1_unreviewed_prs": g1,
            "overlapping_files": overlaps, "g0_ready_for_review":
            not missing and not g0, "g1_contracts_documented":
            not missing and not g1 and not overlaps,
            "combined_behavior_tested": False, "physical_pass": False,
            "deployment_go": False}
