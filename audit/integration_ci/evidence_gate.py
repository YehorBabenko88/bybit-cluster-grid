"""Fail-closed, read-only integration evidence validator. No infrastructure access."""
import argparse
import json
from pathlib import Path

EXPECTED_CASES = 12

def validate(data):
    errors = []
    if not isinstance(data, dict):
        return ["evidence must be a JSON object"]
    for key, expected in (("readiness_passed", False), ("execution_authorized", False), ("schema_2_enabled", False)):
        if type(data.get(key)) is not bool or data[key] is not expected:
            errors.append(f"{key} must be explicit boolean false")
    if data.get("status") not in ("BLOCKED", "BLOCKED_UNPROVEN"):
        errors.append("status must remain BLOCKED or BLOCKED_UNPROVEN")
    cases = data.get("vm_cases")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASES:
        errors.append("exactly 12 VM cases required")
    else:
        ids = [case.get("id") for case in cases if isinstance(case, dict)]
        if len(ids) != EXPECTED_CASES or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != EXPECTED_CASES:
            errors.append("VM case identifiers must be unique nonempty strings")
        for i, case in enumerate(cases):
            if not isinstance(case, dict) or case.get("status") != "NOT_RUN":
                errors.append(f"VM case {i} must be NOT_RUN")
    return errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.evidence.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError) as exc:
        errors = [f"unreadable evidence: {exc}"]
    for error in errors:
        print("BLOCKED:", error)
    if not errors:
        print("PASS: blocked-state invariants only; NOT deployment readiness")
    return int(bool(errors))

if __name__ == "__main__":
    raise SystemExit(main())
