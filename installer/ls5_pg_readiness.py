"""Strict offline PostgreSQL 18 readiness evidence validator.

Does not connect to a DB, inspect a host, or authorize SQL/migration/deployment.
"""
import json
import re
import hashlib

FIELDS = ("service_identity", "db_roles", "db_grants", "filesystem_custody",
          "grid_pg_test_purpose", "migration_inventory", "transaction_isolation",
          "advisory_lock_namespace", "idempotency", "wal_settings",
          "checkpoint_settings", "disk_capacity", "backup_chain",
          "restore_rehearsal", "shutdown_drain", "network_loss",
          "disk_full", "evidence_corruption", "read_only_preflight")
STATES = ("VERIFIED", "FAIL", "UNKNOWN")


def assess(obj):
    fail = lambda why: {"status": "BLOCKED", "reason": why,
                        "physical_verified": False, "deployment_authorized": False}
    if type(obj) is not dict or set(obj) != {"schema", "head", "checks", "physical"}:
        return fail("INVALID_TOP_LEVEL")
    if obj["schema"] != "ls5-pg-readiness-1" or type(obj["head"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", obj["head"]):
        return fail("INVALID_SCHEMA_OR_SHA")
    if obj["physical"] is not False:
        return fail("PHYSICAL_PROMOTION_FORBIDDEN")
    checks = obj["checks"]
    if type(checks) is not dict or set(checks) != set(FIELDS):
        return fail("INCOMPLETE_CHECKS")
    for key in FIELDS:
        value = checks[key]
        if type(value) is not dict or set(value) != {"status", "evidence_sha256"}:
            return fail("INVALID_CHECK")
        if value["status"] not in STATES:
            return fail("INVALID_STATUS")
        digest = value["evidence_sha256"]
        if type(digest) is not str or (digest and not re.fullmatch("[0-9a-f]{64}", digest)):
            return fail("INVALID_DIGEST")
        if value["status"] == "VERIFIED" and not digest:
            return fail("MISSING_EVIDENCE")
    failures = [k for k in FIELDS if checks[k]["status"] == "FAIL"]
    unknown = [k for k in FIELDS if checks[k]["status"] == "UNKNOWN"]
    return {"status": "FAIL" if failures else "BLOCKED" if unknown else "OFFLINE_REVIEW_COMPLETE",
            "failed": failures, "blocked": unknown, "physical_verified": False,
            "deployment_authorized": False, "sql_authorized": False}


def loads_strict(raw):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError("DUPLICATE_KEY")
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))


def verify_payload(receipt, field, payload):
    """Compare receipt digest with exact bytes; never authorize a physical host."""
    if type(payload) is not bytes or type(field) is not str or field not in FIELDS:
        return False
    if type(receipt) is not dict or type(receipt.get("checks")) is not dict:
        return False
    entry = receipt["checks"].get(field)
    if type(entry) is not dict or entry.get("status") != "VERIFIED":
        return False
    expected = entry.get("evidence_sha256")
    return type(expected) is str and bool(re.fullmatch("[0-9a-f]{64}", expected)) and hashlib.sha256(payload).hexdigest() == expected
