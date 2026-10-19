"""Read-only CI status attestation: prevent green-by-omission."""
REQUIRED = frozenset({
    "integration-evidence-audit", "composed-safety-gate",
    "commissioning-manifest", "isolated-postgres-offline",
    "physical-deployment-harness", "windows-commissioning",
    "preflight", "windows-bundle",
})

def assess(runs, expected_sha, required=REQUIRED):
    if not isinstance(runs, list) or not isinstance(expected_sha, str) or len(expected_sha) != 40:
        return {"status": "BLOCKED_UNPROVEN", "reasons": ["invalid input"]}
    seen = {}
    reasons = []
    for run in runs:
        if not isinstance(run, dict):
            reasons.append("malformed run")
            continue
        name = run.get("name")
        if name not in required:
            continue
        if name in seen:
            reasons.append(f"duplicate workflow: {name}")
        seen[name] = run
        if run.get("head_sha") != expected_sha:
            reasons.append(f"wrong SHA: {name}")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            reasons.append(f"not successful: {name}")
    reasons.extend(f"missing workflow: {name}" for name in sorted(required - seen.keys()))
    return {"status": "BLOCKED_UNPROVEN" if reasons else "CI_VERIFIED_ONLY",
            "reasons": reasons,
            "readiness_passed": False,
            "execution_authorized": False}
