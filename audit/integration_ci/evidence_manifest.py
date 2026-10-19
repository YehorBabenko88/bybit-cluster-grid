"""Metadata-only checks. An empty error list authenticates no run or job proof.

The source and synthetic fields are caller assertions, not provenance validation.
"""

import re

CRITICAL = frozenset({
    "integration-evidence-audit", "composed-safety-gate",
    "commissioning-manifest", "isolated-postgres-offline",
    "physical-deployment-harness", "windows-commissioning",
    "preflight", "windows-bundle",
})

def validate_manifest(manifest, expected_sha):
    errors = []
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        errors.append("expected SHA invalid")
    if manifest.get("commit_sha") != expected_sha:
        errors.append("evidence SHA mismatch")
    runs = manifest.get("required_workflows")
    if not isinstance(runs, list) or any(not isinstance(item, str) for item in runs) or len(runs) != len(set(runs)):
        errors.append("required workflows must be unique list")
    elif set(runs) != CRITICAL:
        errors.append("critical workflow coverage incomplete or unexpected")
    if manifest.get("source") != "github-actions":
        errors.append("untrusted evidence source")
    if manifest.get("synthetic") is not False:
        errors.append("synthetic evidence cannot attest readiness")
    return errors
