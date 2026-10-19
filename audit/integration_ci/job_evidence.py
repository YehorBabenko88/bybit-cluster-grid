"""Read-only validation of per-job GitHub Actions evidence.

This function only validates a trusted collector's output; caller dictionaries
cannot authenticate themselves or authorize deployment.
"""
import re

EXPECTED_JOBS = frozenset({"evidence-invariants (3.11)", "evidence-invariants (3.12)"})

def inspect_jobs(jobs, expected_sha, expected_names=EXPECTED_JOBS):
    reasons = []
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        reasons.append("invalid SHA")
    if not isinstance(expected_names, (set, frozenset)) or expected_names != EXPECTED_JOBS:
        reasons.append("job policy override")
    if not isinstance(jobs, list):
        return {"status": "BLOCKED_UNPROVEN", "reasons": reasons + ["invalid jobs"],
                "execution_authorized": False, "readiness_passed": False}
    seen = set()
    if not jobs:
        reasons.append("no jobs")
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("name"), str):
            reasons.append("malformed job")
            continue
        name = job["name"]
        if name not in EXPECTED_JOBS:
            reasons.append("unexpected job")
            continue
        if name in seen:
            reasons.append("duplicate job")
        seen.add(name)
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            reasons.append("job not successful: " + name)
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            reasons.append("missing steps: " + name)
        elif any(not isinstance(step, dict) or step.get("conclusion") != "success" for step in steps):
            reasons.append("failed/skipped step: " + name)
        elif not any(step.get("name") == "Offline negative evidence contract tests" for step in steps):
            reasons.append("required test step missing: " + name)
    for missing in sorted(EXPECTED_JOBS - seen):
        reasons.append("missing job: " + missing)
    return {"status": "BLOCKED_UNPROVEN" if reasons else "CI_JOB_METADATA_ONLY",
            "reasons": reasons, "execution_authorized": False, "readiness_passed": False,
            "note": "No verified run-to-SHA provenance or authenticated GitHub API context"}
