"""Fail-closed metadata-only physical commissioning acceptance; never executes probes."""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET

VERSION = 1
DOMAINS = ("pc4_sid_acl", "windows_logon", "postgres", "network", "vm_lab", "attestation", "production")
PHYSICAL_CASES = tuple(f"{role}_{case}" for role in ("collector", "storage")
                       for case in ("token", "own_write", "own_read", "foreign_read_denied", "foreign_write_denied"))
VM_CASE_COUNT = 12
SHA = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"[a-zA-Z0-9_-]{8,80}\Z")


class AcceptanceBlocked(ValueError):
    """Untrusted or incomplete receipt: never reinterpret as PASS."""


def _require(condition, code):
    if not condition:
        raise AcceptanceBlocked("ACCEPTANCE_" + code)


def _object(value, keys):
    _require(type(value) is dict and set(value) == set(keys), "SCHEMA_INVALID")


def _false_authority(value):
    """Reject positive authority anywhere, including aliases in nested metadata."""
    if type(value) is dict:
        for key, child in value.items():
            if key in ("schema2", "schema2_enabled", "schema_2_enabled",
                       "execution_authorized", "physical_ready", "readiness_passed",
                       "durable_replay_verified", "native_ownership_verified"):
                _require(child is False, "AUTHORITY_FORGED")
            _false_authority(child)
    elif type(value) is list:
        for child in value:
            _false_authority(child)


def validate_receipt(receipt):
    """Validate synthetic/plan-only receipts. Returns BLOCKED, never execution authority.

    Real physical results are not accepted by this offline coordinator: a separate,
    approved native attestation contract and independent review are prerequisites.
    """
    _object(receipt, ("schema", "run_id", "host", "source_sha", "package_sha256",
                      "stage", "mode", "status", "cases", "metadata"))
    _require(type(receipt["schema"]) is int and receipt["schema"] == VERSION, "VERSION")
    _require(type(receipt["run_id"]) is str and RUN.fullmatch(receipt["run_id"]) is not None, "RUN_ID")
    _require(type(receipt["host"]) is str and receipt["host"] in ("PC4", "LS5", "LS7"), "HOST")
    _require(type(receipt["source_sha"]) is str and re.fullmatch(r"[0-9a-f]{40}", receipt["source_sha"]) is not None, "SOURCE_SHA")
    _require(type(receipt["package_sha256"]) is str and SHA.fullmatch(receipt["package_sha256"]) is not None, "PACKAGE_SHA")
    _require(receipt["stage"] in DOMAINS, "STAGE")
    _require(receipt["mode"] == "PLAN_ONLY" and receipt["status"] == "BLOCKED", "EXECUTION_UNAUTHORIZED")
    _require(type(receipt["metadata"]) is dict, "METADATA")
    _false_authority(receipt)
    cases = receipt["cases"]
    _require(type(cases) is list, "CASES")
    if receipt["stage"] == "pc4_sid_acl":
        expected = PHYSICAL_CASES
        _require(receipt["host"] == "PC4", "PC4_HOST")
    elif receipt["stage"] == "vm_lab":
        expected = tuple(f"vm_case_{i:02}" for i in range(1, VM_CASE_COUNT + 1))
    else:
        expected = ()
    _require(len(cases) == len(expected), "CASE_COUNT")
    for case, name in zip(cases, expected):
        _object(case, ("name", "status", "assurance"))
        _require(case["name"] == name and case["status"] == "NOT_RUN"
                 and case["assurance"] == "BLOCKED_UNPROVEN", "CASE_PROMOTION")
    return {"schema": VERSION, "stage": receipt["stage"], "status": "BLOCKED",
            "execution_authorized": False, "physical_ready": False, "schema2": False,
            "verified_cases": 0, "cases_not_run": len(expected),
            "trust": "UNAUTHENTICATED_METADATA_ONLY"}


def verify_jsonl(raw, *, expected_run_id, expected_sha256):
    """Strict UTF-8 LF JSONL digest, no duplicate keys, NaN or malformed roots."""
    _require(type(raw) is bytes and raw and b"\r" not in raw and raw.endswith(b"\n"), "JSONL_BYTES")
    _require(type(expected_sha256) is str and SHA.fullmatch(expected_sha256) is not None, "SHA_FORMAT")
    _require(hashlib.sha256(raw).hexdigest() == expected_sha256, "SHA_MISMATCH")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise AcceptanceBlocked("ACCEPTANCE_JSONL_ENCODING") from None

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AcceptanceBlocked("ACCEPTANCE_DUPLICATE_KEY")
            result[key] = value
        return result

    def invalid_constant(value):
        raise AcceptanceBlocked("ACCEPTANCE_NONFINITE")

    events = []
    for line in text.splitlines():
        _require(bool(line), "EMPTY_LINE")
        try:
            event = json.loads(line, object_pairs_hook=pairs, parse_constant=invalid_constant)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise AcceptanceBlocked("ACCEPTANCE_JSONL_INVALID") from None
        _require(type(event) is dict and event.get("run_id") == expected_run_id, "EVENT_IDENTITY")
        _false_authority(event)
        events.append(event)
    return len(events)


def assess(readiness, *, approvals_verified=False):
    """Aggregate without promoting plan-only or self-reported evidence."""
    _require(type(readiness) is dict and set(readiness) == set(DOMAINS), "MATRIX_SHAPE")
    _require(type(approvals_verified) is bool, "APPROVAL_TYPE")
    for domain, status in readiness.items():
        _require(type(status) is str and status in ("PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_RUN"), "STATUS")
    # FAIL means observed violation; otherwise absent authorization/evidence blocks.
    overall = "FAIL" if "FAIL" in readiness.values() else "BLOCKED"
    return {"status": overall, "deployment_authorized": False,
            "physical_ready": False, "schema2": False,
            "approvals_verified": approvals_verified,
            "reason": "OBSERVED_FAILURE" if overall == "FAIL" else "INDEPENDENT_PHYSICAL_EVIDENCE_UNPROVEN"}


def verify_junit(raw, *, expected_cases, expected_run_id):
    """Strict offline JUnit inventory; not an authenticated physical result."""
    _require(type(raw) is bytes and 0 < len(raw) <= 2_000_000, "JUNIT_BYTES")
    _require(type(expected_cases) is tuple and all(type(x) is str for x in expected_cases)
             and len(expected_cases) == len(set(expected_cases)), "EXPECTED_CASES")
    _require(type(expected_run_id) is str and RUN.fullmatch(expected_run_id) is not None, "RUN_ID")
    _require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "JUNIT_DTD")
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, ValueError):
        raise AcceptanceBlocked("ACCEPTANCE_JUNIT_INVALID") from None
    _require(root.tag == "testsuite", "JUNIT_ROOT")
    _require(root.attrib.get("run_id") == expected_run_id, "JUNIT_IDENTITY")
    _require(set(root.attrib) == {"run_id", "tests", "failures", "errors", "skipped"},
             "JUNIT_ATTRIBUTES")
    _require(all(root.attrib[k].isdigit() for k in ("tests", "failures", "errors", "skipped")),
             "JUNIT_COUNTS")
    cases = list(root)
    _require(len(cases) == len(expected_cases)
             and all(c.tag == "testcase" for c in cases), "JUNIT_CASE_COUNT")
    _require(tuple(c.attrib.get("name") for c in cases) == expected_cases, "JUNIT_CASE_IDENTITY")
    _require(all(set(c.attrib) == {"name"} and len(c) == 1
                 and c[0].tag == "skipped" and not c[0].attrib and not len(c[0])
                 for c in cases), "JUNIT_CASE_PROMOTION")
    _require(int(root.attrib["tests"]) == len(cases)
             and int(root.attrib["skipped"]) == len(cases)
             and int(root.attrib["failures"]) == 0
             and int(root.attrib["errors"]) == 0, "JUNIT_COUNT_MISMATCH")
    return {"status": "BLOCKED", "cases_not_run": len(cases), "physical_ready": False}


def verify_sha256_index(index_raw, files):
    """Check a self-consistent evidence bundle, not provenance or authorization."""
    _require(type(index_raw) is bytes and 0 < len(index_raw) <= 1_000_000, "INDEX_BYTES")
    _require(type(files) is dict and files, "FILES")
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        index = json.loads(index_raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise AcceptanceBlocked("ACCEPTANCE_INDEX_INVALID") from None
    _require(type(index) is dict and set(index) == {"schema", "files"}
             and type(index["schema"]) is int and index["schema"] == 1
             and type(index["files"]) is dict, "INDEX_SCHEMA")
    _require(set(index["files"]) == set(files), "INDEX_INVENTORY")
    for name, content in files.items():
        _require(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)
                 and name not in ("sha256.json", "completed.json"), "FILE_NAME")
        _require(type(content) is bytes, "FILE_BYTES")
        digest = index["files"][name]
        _require(type(digest) is str and SHA.fullmatch(digest) is not None, "INDEX_SHA_FORMAT")
        _require(hashlib.sha256(content).hexdigest() == digest, "INDEX_SHA_MISMATCH")
    return {"status": "BLOCKED", "files_verified": len(files),
            "provenance_verified": False, "physical_ready": False}
