"""Run strict node-level Grid or source-custody test obligations.

Every execution is a separate Python process.  No skip, xfail, deselection,
missing phase or duplicate report can count as a passing obligation.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

GRID = Path(__file__).resolve().parents[1]
PARTITION = runpy.run_path(str(GRID / "scripts" / "check_cross_repo_roster_partition.py"))
Guard = runpy.run_path(str(GRID / "scripts" / "canonical_test_gate.py"))["StrictTestRoster"]
SOURCE_SHA = PARTITION["SOURCE_SHA"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True, choices=("grid", "custody"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    report = args.evidence.absolute()
    if report.exists():
        raise RuntimeError("evidence must be a new file")
    mapping = PARTITION["validate"]()
    # Some subprocess-isolation tests restore os.environ on Windows, where
    # empty inherited Git config values can disappear. Preserve the original
    # Git environment for both exact checkout identity queries.
    git_env = os.environ.copy()
    if args.scope == "grid":
        root = GRID
        nodes = mapping["grid_nodes"]
    else:
        if args.source_root is None:
            raise RuntimeError("pinned source checkout required")
        root = args.source_root.resolve(strict=True)
        if root == GRID or root.is_relative_to(GRID / "scripts"):
            raise RuntimeError("source root cannot alias Grid source")
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True, env=git_env,
        ).strip()
        if head != SOURCE_SHA:
            raise RuntimeError("source SHA differs from sealed custody pin")
        nodes = mapping["custody_nodes"]
    if args.scope == "grid" and args.source_root is not None:
        raise RuntimeError("Grid execution must not use source override")
    for node in nodes:
        part = node.split("::", 1)[0]
        candidate = root / part
        if not candidate.is_file() or candidate.is_symlink():
            raise RuntimeError("missing or linked test source: " + part)
    absolute = [str(root / n.split("::", 1)[0])
                + ("::" + n.split("::", 1)[1] if "::" in n else "")
                for n in nodes]
    guard = Guard(nodes, expected_count=len(nodes))
    # Tests are deliberately run from the source tree for correct sealed
    # self-relative archives; no production network or credentials supplied.
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.chdir(root)
    # Importlib mode does not add sibling fixture modules to sys.path.
    # These are test-only roots; runtime modules still come from the installed wheel.
    sys.path[:0] = [str(root / "tests" / "market_data"),
                    str(root / "tests" / "marketdata")]
    import pytest
    result = pytest.main([
        "--rootdir", str(root),
        "--import-mode=importlib",
        "-p", "pytest_asyncio.plugin",
        "-p", "no:cacheprovider",
        "-q",
        *absolute,
    ], plugins=[guard])
    outcome = {
        "schema": "grid.market_data.strict_partition_execution.v1",
        "scope": args.scope,
        "source_sha": SOURCE_SHA,
        "grid_head": subprocess.check_output(
            ["git", "-C", str(GRID), "rev-parse", "HEAD"], text=True, env=git_env
        ).strip(),
        "node_count": len(nodes),
        "total_required": mapping["total"],
        "three_phase_reports": len(guard.reports),
        "accepted": result == 0 and guard.accepted,
        "errors": guard.errors[:16],
    }
    report.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
