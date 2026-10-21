"""Validate a supplied offline JSON report; never connect to Windows hosts."""
import argparse
import json
from pathlib import Path

from .contracts import assess_inventory, assess_logon


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-only infrastructure readiness classifier")
    parser.add_argument("report", type=Path)
    parser.add_argument("--kind", choices=("inventory", "logon"), default="inventory")
    args = parser.parse_args()
    # File is supplied explicitly by the operator. No network, LSA or subprocess use.
    try:
        data = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "issues": ["INVALID_REPORT_FILE"],
                          "readiness_passed": False, "execution_authorized": False}))
        return 2
    result = assess_inventory(data) if args.kind == "inventory" else assess_logon(data)
    print(json.dumps({"status": result.status, "issues": result.issues,
                      "readiness_passed": result.readiness_passed,
                      "execution_authorized": result.execution_authorized,
                      "physical_cases": result.physical_cases}, indent=2))
    return 2 if result.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
