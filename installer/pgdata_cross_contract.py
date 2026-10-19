"""Offline cross-contract PGDATA checks. Metadata never grants execution authority."""
from pathlib import PureWindowsPath
from installer.isolated_postgres_plan import validate_postgres_plan, ProvisioningBlocked


def inspect_producer_journal_format(journal):
    """Read-only shape check; never establishes journal provenance or authority."""
    import json
    import re
    if type(journal) not in (str, bytes):
        return "JOURNAL_FORMAT_INVALID"
    try:
        value = journal.decode("utf-8") if type(journal) is bytes else journal
        encoded = value.encode("utf-8")
    except UnicodeError:
        return "JOURNAL_ENCODING_INVALID"
    if not value or len(encoded) > 4096 or not value.endswith("\n") or "\r" in value or value.startswith("\ufeff"):
        return "JOURNAL_NONCANONICAL_BYTES"
    records = []
    for line in value[:-1].split("\n"):
        try:
            pairs = json.loads(line, object_pairs_hook=lambda items: items,
                               parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        except (ValueError, UnicodeError, RecursionError):
            return "JOURNAL_FORMAT_INVALID"
        # object_pairs_hook returns lists for JSON objects, but JSON arrays are
        # also lists. Never destructure elements before validating their shape.
        if (type(pairs) is not list or len(pairs) != 3
                or any(type(pair) is not tuple or len(pair) != 2
                       or type(pair[0]) is not str for pair in pairs)):
            return "JOURNAL_RECORD_SCHEMA_INVALID"
        if [pair[0] for pair in pairs] != ["schema", "plan_sha256", "state"]:
            return "JOURNAL_RECORD_SCHEMA_INVALID"
        schema, digest, state = (pair[1] for pair in pairs)
        if type(schema) is not int or schema != 1 or type(digest) is not str or re.fullmatch("[0-9a-f]{64}", digest) is None or type(state) is not str or state not in ("PREPARED", "COMMITTED", "RETIRED"):
            return "JOURNAL_RECORD_SCHEMA_INVALID"
        canonical = '{"schema":1,"plan_sha256":"' + digest + '","state":"' + state + '"}'
        if line != canonical:
            return "JOURNAL_NONCANONICAL_BYTES"
        records.append((digest, state))
    if [state for digest, state in records] not in (["PREPARED"], ["PREPARED", "COMMITTED"], ["PREPARED", "RETIRED"], ["PREPARED", "COMMITTED", "RETIRED"]):
        return "JOURNAL_LIFECYCLE_INVALID"
    if len({digest for digest, state in records}) != 1:
        return "JOURNAL_DIGEST_MISMATCH"
    return "JOURNAL_PRODUCER_JSONL_NOT_DIAGNOSTIC_ENVELOPE"

def check_pgdata_contract(plan, adapter, journal):
    result = {"status": "BLOCKED", "readiness_passed": False,
              "execution_authorized": False, "physical_ready": False,
              "ownership_verified": False, "schema2_enabled": False,
              "blockers": []}
    try:
        validate_postgres_plan(plan)
    except (ProvisioningBlocked, TypeError, ValueError, KeyError) as exc:
        result["blockers"].append("PLAN_INVALID")
        return result
    if type(adapter) is not dict:
        result["blockers"].append("ADAPTER_MISSING")
    else:
        if (type(adapter.get("run_id")) is not str or adapter["run_id"] != plan["run_id"]
                or type(adapter.get("node_id")) is not str or adapter["node_id"] != plan["node_id"]
                or type(adapter.get("postgres_port")) is not int or adapter["postgres_port"] != plan["port"]):
            result["blockers"].append("ADAPTER_IDENTITY_MISMATCH")
        root = adapter.get("root")
        # PowerShell GridLab root is <parent>\\<run_id>_<node_id>, not schema-1 PGDATA.
        if type(root) is not str or str(PureWindowsPath(root) / "postgres" / "data") != plan["data_root"]:
            result["blockers"].append("PGDATA_LAYOUT_MISMATCH")
    if type(journal) is not dict:
        result["blockers"].append(inspect_producer_journal_format(journal) if type(journal) in (str, bytes) else "JOURNAL_MISSING")
    else:
        if set(journal) != {"status", "execution_authorized", "readiness_passed", "run_id", "node_id", "pgdata"}:
            result["blockers"].append("JOURNAL_ENVELOPE_SCHEMA_INVALID")
        if journal.get("execution_authorized") is not False or journal.get("readiness_passed") is not False:
            result["blockers"].append("JOURNAL_AUTHORIZATION_FORBIDDEN")
        if type(journal.get("status")) is not str:
            result["blockers"].append("JOURNAL_FIELD_TYPE_INVALID")
        elif journal["status"] != "BLOCKED":
            result["blockers"].append("JOURNAL_STATUS_UNSAFE")
        if type(journal.get("run_id")) is not str or type(journal.get("node_id")) is not str:
            result["blockers"].append("JOURNAL_FIELD_TYPE_INVALID")
        elif journal["run_id"] != plan["run_id"] or journal["node_id"] != plan["node_id"]:
            result["blockers"].append("JOURNAL_IDENTITY_MISMATCH")
        if type(journal.get("pgdata")) is not str:
            result["blockers"].append("JOURNAL_FIELD_TYPE_INVALID")
        elif journal["pgdata"] != plan["data_root"]:
            result["blockers"].append("JOURNAL_PGDATA_MISMATCH")
    # Even matching metadata is not proof of physical path identity, ACL or ownership.
    result["blockers"].append("PHYSICAL_OWNERSHIP_UNVERIFIED")
    result["blockers"].append("SCHEMA1_ADAPTER_MAPPING_BLOCKED")
    result["blockers"] = sorted(set(result["blockers"]))
    return result
