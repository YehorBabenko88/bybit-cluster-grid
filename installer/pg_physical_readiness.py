"""Fail-closed PostgreSQL physical readiness verdict, independent of CI PASS.

Offline-only. No connections, mutations, or authority grants.
"""
import json
import re

REQUIRED = (
    "ls5_host_identity", "ls5_postgres_service_identity", "ls5_cluster_system_identifier",
    "existing_database_inventory", "existing_role_inventory", "existing_wal_custody",
    "existing_backup_custody", "dsn_allowlist_and_worker_boundary",
    "isolated_pg18_cluster_identity", "isolated_storage_and_port",
    "generated_db_and_roles_ownership", "migration_1_48_and_schema_seal",
    "runtime_ddl_denial", "synthetic_market_data_integrity",
    "concurrent_idempotency", "transaction_rollback", "advisory_lock_release",
    "isolated_backup_restore", "isolated_crash_recovery",
    "cleanup_receipt_and_no_foreign_drop", "owner_g1_authorization",
)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_KEY")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))


def verdict(receipt):
    blocked = {"verdict": "BLOCKED", "physical_execute_authorized": False,
               "deployment_authorized": False, "physical_tests": "0/10 NOT_RUN"}
    if type(receipt) is not dict or set(receipt) != {"schema", "head", "checks"}:
        return dict(blocked, reason="INVALID_RECEIPT")
    if receipt["schema"] != "pg-physical-readiness-1" or type(receipt["head"]) is not str or not re.fullmatch("[0-9a-f]{40}", receipt["head"]):
        return dict(blocked, reason="INVALID_HEAD")
    checks = receipt["checks"]
    if type(checks) is not dict or set(checks) != set(REQUIRED):
        return dict(blocked, reason="INCOMPLETE_INVENTORY")
    for name in REQUIRED:
        value = checks[name]
        if (type(value) is not dict or set(value) != {"status", "evidence_sha256"}
                or value["status"] not in ("VERIFIED", "FAIL", "UNKNOWN")
                or type(value["evidence_sha256"]) is not str
                or (value["status"] == "VERIFIED" and not re.fullmatch("[0-9a-f]{64}", value["evidence_sha256"]))):
            return dict(blocked, reason="INVALID_CHECK", field=name)
    failed = [k for k in REQUIRED if checks[k]["status"] == "FAIL"]
    unknown = [k for k in REQUIRED if checks[k]["status"] == "UNKNOWN"]
    if failed:
        return dict(blocked, verdict="NO-GO", reason="FAILED_CHECKS", checks=failed)
    if unknown:
        return dict(blocked, reason="UNPROVEN_CHECKS", checks=unknown)
    # Self-reported digests do not attest to the actual bytes, source, or owner approval.
    return dict(blocked, reason="SELF_REPORTED_EVIDENCE_NOT_ATTESTATION")


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.receipt.stat().st_size > 65536:
            raise ValueError("TOO_LARGE")
        result = verdict(strict_json(args.receipt.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError, TypeError):
        result = {"verdict": "BLOCKED", "reason": "INVALID_INPUT",
                  "physical_execute_authorized": False,
                  "deployment_authorized": False, "physical_tests": "0/10 NOT_RUN"}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(2)
