"""Fail-closed, dedicated pytest/JUnit receipt checker for PostgreSQL cross-contract.

CI must supply exact HEAD SHA and execute this only after a strict pytest run.
A receipt is test coverage evidence, never physical readiness.
"""
import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

TARGET = "tests/test_pgdata_cross_contract.py"
MIN_TESTS = 23


def validate_receipt(xml_text, commit_sha, expected_sha):
    errors = []
    if (type(commit_sha) is not str or not re.fullmatch(r"[0-9a-f]{40}", commit_sha)
            or commit_sha != expected_sha):
        errors.append("HEAD_SHA_MISMATCH")
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError, ValueError):
        return errors + ["INVALID_JUNIT_XML"]
    cases = list(root.iter("testcase"))
    matched = [
        case for case in cases
        if ("test_pgdata_cross_contract" in case.attrib.get("classname", "")
            or "test_pgdata_cross_contract" in case.attrib.get("file", ""))
    ]
    if len(matched) < MIN_TESTS:
        errors.append("PG_CROSS_CONTRACT_CASES_MISSING")
    if len(matched) != len(cases):
        errors.append("UNEXPECTED_TEST_SCOPE")
    for case in cases:
        if any(case.find(tag) is not None for tag in ("skipped", "failure", "error")):
            errors.append("SKIPPED_OR_FAILED_CASE")
            break
    if not cases:
        errors.append("ZERO_TESTS")
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--junit", required=True, type=Path)
    p.add_argument("--sha", required=True)
    p.add_argument("--expected-sha", required=True)
    args = p.parse_args()
    try:
        errors = validate_receipt(args.junit.read_text(encoding="utf-8"), args.sha, args.expected_sha)
    except (OSError, UnicodeError):
        errors = ["MISSING_JUNIT_RECEIPT"]
    print("BLOCKED_UNPROVEN:", ",".join(errors) if errors else
          "PG pytest receipt checked; physical ownership and readiness unverified")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
