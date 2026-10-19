"""Read-only comparison of real installer journal JSONL and isolated PG plan.

No physical ownership, ACL, runtime identity, or execution authority is inferred.
"""
import json

ALLOWED_STATES = (
    ("PREPARED",),
    ("PREPARED", "COMMITTED"),
    ("PREPARED", "RETIRED"),
    ("PREPARED", "COMMITTED", "RETIRED"),
)

def inspect_journal_bytes(journal_text, plan_sha256):
    errors = []
    if not isinstance(plan_sha256, str) or len(plan_sha256) != 64 or any(c not in "0123456789abcdef" for c in plan_sha256):
        errors.append("invalid plan digest")
    if not isinstance(journal_text, str) or not journal_text or len(journal_text.encode("utf-8")) > 4096:
        errors.append("invalid journal bounds")
        return _result(errors)
    if not journal_text.endswith("\n"):
        errors.append("missing terminal newline")
    states = []
    for line in journal_text.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            errors.append("invalid JSONL record")
            continue
        if not isinstance(row, dict) or set(row) != {"schema", "plan_sha256", "state"}:
            errors.append("unexpected journal record schema")
            continue
        if type(row["schema"]) is not int or row["schema"] != 1:
            errors.append("schema-1 required")
        if row["plan_sha256"] != plan_sha256:
            errors.append("plan digest mismatch")
        states.append(row["state"])
    if tuple(states) not in ALLOWED_STATES:
        errors.append("illegal journal transition")
    return _result(errors)

def _result(errors):
    return {"status": "BLOCKED_UNPROVEN", "metadata_valid": not errors,
            "errors": errors, "readiness_passed": False,
            "execution_authorized": False, "schema_2_enabled": False,
            "physical_ownership_verified": False,
            "note": "Journal metadata is not authenticated physical ownership evidence"}
