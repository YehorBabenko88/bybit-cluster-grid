"""Caller-supplied CI metadata checks; never authenticated workflow/job proof."""
import re

REQUIRED = frozenset({
    "integration-evidence-audit", "composed-safety-gate",
    "commissioning-manifest", "isolated-postgres-offline",
    "physical-deployment-harness", "windows-commissioning",
    "preflight", "windows-bundle",
})

def assess(runs, expected_sha, required=REQUIRED):
    if (not isinstance(runs, list) or not isinstance(expected_sha, str)
            or re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None
            or not isinstance(required, (set, frozenset)) or required != REQUIRED):
        return {"status": "BLOCKED_UNPROVEN", "reasons": ["invalid input"],
                "readiness_passed": False, "execution_authorized": False}
    seen = {}
    reasons = []
    for run in runs:
        if not isinstance(run, dict):
            reasons.append("malformed run")
            continue
        name = run.get("name")
        if not isinstance(name, str):
            reasons.append("malformed workflow name")
            continue
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
    return {"status": "BLOCKED_UNPROVEN" if reasons else "CI_METADATA_ONLY",
            "reasons": reasons,
            "evidence_scope": "caller-supplied run metadata; job execution and provenance unverified",
            "readiness_passed": False,
            "execution_authorized": False}
