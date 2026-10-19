"""Offline integration risk report. Deliberately does not imply merge safety."""
import json
from .branch_overlap import audit as path_audit
from .workflow_attestation import assess as ci_assess

def report(branch_files, workflow_runs, expected_sha):
    paths = path_audit(branch_files)
    ci = ci_assess(workflow_runs, expected_sha)
    blockers = []
    if paths["conflicts"]:
        blockers.append("overlapping paths require human reconciliation")
    if ci["status"] != "CI_VERIFIED_ONLY":
        blockers.append("required CI evidence incomplete")
    blockers.extend([
        "cross-branch semantic compatibility unverified",
        "physical VM principal/ACL tests NOT_RUN (12 cases)",
        "schema-2 activation prohibited",
        "production deployment unauthorized",
    ])
    return {
        "status": "BLOCKED_UNPROVEN",
        "readiness_passed": False,
        "execution_authorized": False,
        "schema_2_enabled": False,
        "vm_case_count": 12,
        "vm_case_status": "NOT_RUN",
        "path_audit": paths,
        "ci_attestation": ci,
        "blockers": blockers,
    }

def to_json(result):
    return json.dumps(result, sort_keys=True, indent=2)
