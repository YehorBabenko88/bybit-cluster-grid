"""Offline CI evidence receipt; never authorizes host execution."""
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: evidence.py JUNIT.xml OUTDIR")
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    if not source.is_file():
        raise SystemExit("missing junit")
    root = ET.parse(source).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites or any(s.tag != "testsuite" for s in suites):
        raise SystemExit("invalid junit suites")
    cases = [c for s in suites for c in s.iter("testcase")]
    if not cases:
        raise SystemExit("zero collected tests")
    failures = [c for c in cases if any(c.find(tag) is not None for tag in ("failure", "error"))]
    skips = [c for c in cases if c.find("skipped") is not None]
    head = os.environ.get("GITHUB_SHA", "")
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise SystemExit("invalid exact HEAD")
    output.mkdir(parents=True, exist_ok=True)
    junit_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    events = [
        {"schema": "grid-ls5-bootstrap-ci-1", "event": "identity", "head": head,
         "run_id": os.environ.get("GITHUB_RUN_ID", ""), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
         "runner_os": os.environ.get("RUNNER_OS", ""), "python": sys.version.split()[0],
         "junit_sha256": junit_hash},
        {"schema": "grid-ls5-bootstrap-ci-1", "event": "test_summary", "head": head,
         "collected": len(cases), "failed": len(failures), "skipped": len(skips),
         "status": "PASS" if not failures and not skips else "BLOCKED",
         "physical_tests": "0/10 NOT_RUN", "execute_authorized": False,
         "cleanup_authorized": False, "deployment_authorized": False},
    ]
    jsonl = output / "evidence.jsonl"
    jsonl.write_text("".join(json.dumps(x, sort_keys=True, separators=(",", ":")) + "\n" for x in events), encoding="utf-8")
    manifest = {"schema": "grid-ls5-bootstrap-hashes-1", "head": head,
                "files": {"junit.xml": junit_hash, "evidence.jsonl": hashlib.sha256(jsonl.read_bytes()).hexdigest()}}
    (output / "hashes.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output / "junit.xml").write_bytes(source.read_bytes())
    if failures or skips:
        raise SystemExit("test evidence not PASS")

if __name__ == "__main__":
    main()
