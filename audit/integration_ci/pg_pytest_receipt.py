"""Strict offline pytest collection/JUnit reconciliation; never physical authority."""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

TARGET = "tests/test_pgdata_cross_contract.py"
CLASSNAME = "tests.test_pgdata_cross_contract"


def _collected_ids(collection):
    if type(collection) is not list or not collection:
        return None
    ids = []
    for entry in collection:
        if type(entry) is not str or not re.fullmatch(
                r"tests/test_pgdata_cross_contract\.py::test_[A-Za-z0-9_]+", entry):
            return None
        ids.append(entry)
    return ids if len(set(ids)) == len(ids) else None


def validate_receipt(xml_text, commit_sha, expected_sha, collected_ids=None):
    errors = []
    if (type(commit_sha) is not str or not re.fullmatch(r"[0-9a-f]{40}", commit_sha)
            or commit_sha != expected_sha):
        errors.append("HEAD_SHA_MISMATCH")
    expected = _collected_ids(collected_ids)
    if expected is None:
        errors.append("COLLECTION_REQUIRED")
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError, ValueError):
        return errors + ["INVALID_JUNIT_XML"]
    if root.tag not in ("testsuite", "testsuites"):
        errors.append("INVALID_JUNIT_ROOT")
    cases = list(root.iter("testcase"))
    if len(cases) > 10000:
        errors.append("JUNIT_CASE_LIMIT_EXCEEDED")
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        errors.append("JUNIT_SUITE_MISSING")
    for suite in suites:
        for attribute, actual in (("tests", len(list(suite.iter("testcase")))),
                                  ("failures", len(list(suite.iter("failure")))),
                                  ("errors", len(list(suite.iter("error")))),
                                  ("skipped", len(list(suite.iter("skipped"))))):
            declared = suite.attrib.get(attribute)
            if declared is not None and (not declared.isdecimal() or int(declared) != actual):
                errors.append("JUNIT_SUITE_COUNTS_MISMATCH")
                break
    actual_ids = []
    for case in cases:
        name = case.attrib.get("name")
        classname = case.attrib.get("classname")
        file_path = case.attrib.get("file")
        if (classname != CLASSNAME or type(name) is not str or
                re.fullmatch(r"test_[A-Za-z0-9_]+", name) is None or
                (file_path is not None and file_path != TARGET)):
            errors.append("UNEXPECTED_TEST_SCOPE")
            continue
        actual_ids.append(TARGET + "::" + name)
    if not cases:
        errors.append("ZERO_TESTS")
    if len(actual_ids) != len(set(actual_ids)):
        errors.append("DUPLICATE_TESTCASE")
    if expected is not None and (len(actual_ids) != len(expected) or
                                 set(actual_ids) != set(expected)):
        errors.append("COLLECTION_JUNIT_MISMATCH")
    for case in cases:
        if any(case.find(tag) is not None for tag in ("skipped", "failure", "error")):
            errors.append("SKIPPED_OR_FAILED_CASE")
            break
    if any(node.tag in ("skipped", "failure", "error") for node in root.iter()):
        errors.append("SKIPPED_OR_FAILED_CASE")
    if any(node.tag in ("testcase", "testsuite", "testsuites") and node is not root and
           node not in cases and node not in suites for node in root.iter()):
        errors.append("UNEXPECTED_JUNIT_STRUCTURE")
    return list(dict.fromkeys(errors))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--junit", required=True, type=Path)
    p.add_argument("--collected", required=True, type=Path)
    p.add_argument("--sha", required=True)
    p.add_argument("--expected-sha", required=True)
    args = p.parse_args()
    try:
        collected = json.loads(args.collected.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        collected = None
    try:
        report = args.junit.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        report = ""
    errors = validate_receipt(report, args.sha, args.expected_sha, collected)
    print("BLOCKED_UNPROVEN:", ",".join(errors) if errors else
          "exact PG pytest inventory matched; physical ownership and readiness unverified")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
