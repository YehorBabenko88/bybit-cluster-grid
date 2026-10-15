"""Fail-closed, read-only validation for isolated PostgreSQL 16 provisioning plans.

This module intentionally does not invoke initdb, pg_ctl, SQL, or filesystem
mutations. It validates an operator-supplied plan before any future executor
is considered. Never use this validator as proof of filesystem ownership.
"""
import ipaddress
import re
from pathlib import PureWindowsPath


class ProvisioningBlocked(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise ProvisioningBlocked(code)


def validate_postgres_plan(plan):
    """Return normalized metadata only; no permission to provision."""
    _require(type(plan) is dict, "PLAN_INVALID")
    expected = {"schema", "run_id", "node_id", "data_root", "port",
                "postgres_major", "listen_address", "existing_cluster",
                "runtime_stopped", "operator_approved"}
    _require(set(plan) == expected, "PLAN_SCHEMA_INVALID")
    _require(type(plan["schema"]) is int and plan["schema"] == 1, "PLAN_VERSION_INVALID")
    run_id = plan["run_id"]
    node_id = plan["node_id"]
    _require(type(run_id) is str and re.fullmatch(r"[0-9a-f]{32}", run_id), "RUN_ID_INVALID")
    _require(type(node_id) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,15}", node_id), "NODE_INVALID")
    _require(node_id.upper() not in {"LS5", "LS7"}, "PROTECTED_NODE")
    root = plan["data_root"]
    _require(type(root) is str and len(root) < 240 and not any(ord(c) < 32 for c in root), "ROOT_INVALID")
    _require(not re.search(r"(^|[\\/])\.{1,2}([\\/]|$)", root), "ROOT_TRAVERSAL")
    path = PureWindowsPath(root)
    _require(path.is_absolute() and re.fullmatch(r"[A-Za-z]:", path.drive or ""), "ROOT_NOT_LOCAL_DRIVE")
    _require(tuple(p.casefold() for p in path.parts[-4:]) ==
             ("gridlab", run_id, node_id.casefold(), "pgdata"), "ROOT_NOT_ISOLATED")
    _require(not any(p.casefold() in {"windows", "program files", "programdata"} for p in path.parts[1:]), "ROOT_PROTECTED")
    _require(type(plan["port"]) is int and 1024 <= plan["port"] <= 65535, "PORT_INVALID")
    _require(type(plan["postgres_major"]) is int and plan["postgres_major"] == 16, "POSTGRES_VERSION_INVALID")
    address = plan["listen_address"]
    _require(type(address) is str, "LISTEN_ADDRESS_INVALID")
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ProvisioningBlocked("LISTEN_ADDRESS_INVALID") from exc
    _require(ip.is_loopback, "LISTEN_ADDRESS_NOT_LOOPBACK")
    _require(plan["existing_cluster"] is False, "EXISTING_CLUSTER_FORBIDDEN")
    _require(plan["runtime_stopped"] is True, "RUNTIME_NOT_STOPPED")
    # An operator-approved plan is still NOT execution authorization.
    _require(plan["operator_approved"] is True, "APPROVAL_REQUIRED")
    return {"status": "VALIDATED_PLAN_ONLY", "execution_authorized": False,
            "physical_ready": False, "run_id": run_id, "node_id": node_id,
            "data_root": str(path), "port": plan["port"],
            "listen_address": str(ip), "postgres_major": 16,
            "blockers": ["FRESH_HOST_INVENTORY_REQUIRED",
                         "PATH_OWNERSHIP_AND_ACL_NOT_VERIFIED",
                         "BINARY_PROVENANCE_NOT_VERIFIED",
                         "PORT_BIND_NOT_RESERVED",
                         "NO_INITDB_EXECUTOR"]}
