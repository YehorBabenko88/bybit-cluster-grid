"""Read-only policy checks for evidence metadata and critical workflow selection."""

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
    if not isinstance(expected_sha, str) or len(expected_sha) != 40:
        errors.append("expected SHA invalid")
    if manifest.get("commit_sha") != expected_sha:
        errors.append("evidence SHA mismatch")
    runs = manifest.get("required_workflows")
    if not isinstance(runs, list) or len(runs) != len(set(runs)) if isinstance(runs, list) else True:
        errors.append("required workflows must be unique list")
    elif set(runs) != CRITICAL:
        errors.append("critical workflow coverage incomplete or unexpected")
    if manifest.get("source") != "github-actions":
        errors.append("untrusted evidence source")
    if manifest.get("synthetic") is not False:
        errors.append("synthetic evidence cannot attest readiness")
    return errors
