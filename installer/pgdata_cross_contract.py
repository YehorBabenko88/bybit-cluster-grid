"""Offline cross-contract PGDATA checks. Metadata never grants execution authority."""
from pathlib import PureWindowsPath
from installer.isolated_postgres_plan import validate_postgres_plan, ProvisioningBlocked

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
        if type(root) is not str or str(PureWindowsPath(root) / "postgres" / "data") != plan["data_root"]:
            result["blockers"].append("PGDATA_LAYOUT_MISMATCH")
    if type(journal) is not dict:
        result["blockers"].append("JOURNAL_MISSING")
    else:
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
