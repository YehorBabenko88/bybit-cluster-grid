"""Pure-data validation of Windows infrastructure observations.

Untrusted input is never promoted to physical execution authorization.
"""
from dataclasses import dataclass
from typing import Mapping, Tuple

STATES = frozenset(("PASS", "BLOCKED", "UNKNOWN"))
CONTROLS = (
    "ls5_identity", "pc4_identity", "ssh_auth", "ssh_authorization",
    "tailscale_identity", "tailscale_policy", "firewall_routes",
    "local_principals", "effective_interactive_logon", "seclogon_running",
    "acl_owner_dacl", "acl_effective_access", "package_integrity",
    "token_independence", "witness_independence",
)
BLOCKING = frozenset(("effective_interactive_logon", "seclogon_running",
                      "local_principals", "acl_owner_dacl",
                      "acl_effective_access", "token_independence"))


@dataclass(frozen=True)
class Assessment:
    status: str
    issues: Tuple[str, ...]
    readiness_passed: bool = False
    execution_authorized: bool = False
    physical_cases: Tuple[str, ...] = ("NOT_RUN",) * 10


def assess_inventory(inventory: object) -> Assessment:
    """No caller-provided PASS or readiness flag can authorize execution."""
    issues = []
    if not isinstance(inventory, Mapping):
        return Assessment("BLOCKED", ("INVALID_INVENTORY",))
    if inventory.get("schema_version") != 1 or type(inventory.get("schema_version")) is not int:
        issues.append("INVALID_SCHEMA_VERSION")
    if inventory.get("readiness_passed") is not False:
        issues.append("READINESS_MUST_BE_FALSE")
    if inventory.get("execution_authorized") is not False:
        issues.append("EXECUTION_MUST_BE_FALSE")
    if inventory.get("physical_cases") != ["NOT_RUN"] * 10:
        issues.append("PHYSICAL_CASES_MUST_BE_NOT_RUN")
    controls = inventory.get("controls")
    if not isinstance(controls, Mapping):
        return Assessment("BLOCKED", tuple(issues + ["INVALID_CONTROLS"]))
    for name in CONTROLS:
        record = controls.get(name)
        if not isinstance(record, Mapping):
            issues.append(f"{name}:MISSING")
            continue
        status = record.get("status")
        if type(status) is not str or status not in STATES:
            issues.append(f"{name}:INVALID_STATUS")
            continue
        if status != "PASS":
            issues.append(f"{name}:{status}")
        # A PASS without independent witness is an unverified assertion.
        if status == "PASS":
            source = record.get("evidence_ref")
            witness = record.get("witness_ref")
            if (type(source) is not str or not source.strip() or
                    type(witness) is not str or not witness.strip() or
                    source == witness):
                issues.append(f"{name}:UNVERIFIED_PASS")
    for name in controls:
        if type(name) is not str or name not in CONTROLS:
            issues.append("UNKNOWN_CONTROL")
    status = "BLOCKED" if any(
        i.split(":")[0] in BLOCKING or i in (
            "INVALID_INVENTORY", "INVALID_SCHEMA_VERSION", "INVALID_CONTROLS",
            "READINESS_MUST_BE_FALSE", "EXECUTION_MUST_BE_FALSE",
            "PHYSICAL_CASES_MUST_BE_NOT_RUN") for i in issues
    ) else "UNKNOWN"
    return Assessment(status, tuple(issues or ["OFFLINE_EVIDENCE_NOT_EXECUTION_PROOF"]))


def assess_logon(observation: object) -> Assessment:
    """Check the *reported* interactive logon path; no LSA query or logon attempt."""
    if not isinstance(observation, Mapping):
        return Assessment("BLOCKED", ("INVALID_LOGON_OBSERVATION",))
    issues = []
    if observation.get("launcher") != "CreateProcessWithLogonW":
        issues.append("LAUNCHER_UNVERIFIED")
    if observation.get("logon_type") != "interactive":
        issues.append("INTERACTIVE_LOGON_UNVERIFIED")
    if observation.get("seclogon_state") != "Running":
        issues.append("SECLOGON_NOT_CONFIRMED_RUNNING")
    for role in ("collector", "storage"):
        data = observation.get(role)
        if not isinstance(data, Mapping):
            issues.append(f"{role}:MISSING")
            continue
        for field in ("account_enabled", "effective_interactive_allow",
                      "effective_interactive_deny_absent", "non_admin",
                      "acl_isolated"):
            if data.get(field) is not True:
                issues.append(f"{role}:{field}_NOT_PROVEN")
        if data.get("effective_interactive_deny_absent") is not True:
            issues.append(f"{role}:DENY_OVERRIDES_ALLOW_OR_UNKNOWN")
    return Assessment("BLOCKED", tuple(issues or ["LOGON_REPORT_IS_NOT_TOKEN_PROOF"]))
