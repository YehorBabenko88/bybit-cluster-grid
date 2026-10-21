"""Pure offline tests. No VM, Windows API, service or network access."""
from infra_readiness.contracts import CONTROLS, assess_inventory, assess_logon


def baseline():
    return dict(schema_version=1, readiness_passed=False,
                execution_authorized=False, physical_cases=["NOT_RUN"] * 10,
                controls={name: {"status": "UNKNOWN"} for name in CONTROLS})


def test_unknown_inventory_never_authorizes():
    result = assess_inventory(baseline())
    assert result.status == "BLOCKED"
    assert not result.readiness_passed and not result.execution_authorized
    assert result.physical_cases == ("NOT_RUN",) * 10


def test_network_success_not_equivalent_to_isolation():
    data = baseline()
    for name in ("ssh_auth", "tailscale_identity", "firewall_routes"):
        data["controls"][name] = {"status": "PASS", "evidence_ref": "e1", "witness_ref": "w2"}
    result = assess_inventory(data)
    assert result.status == "BLOCKED"
    assert "token_independence:UNKNOWN" in result.issues


def test_forged_pass_requires_distinct_provenance():
    data = baseline()
    data["controls"]["local_principals"] = {
        "status": "PASS", "evidence_ref": "same", "witness_ref": "same"}
    assert "local_principals:UNVERIFIED_PASS" in assess_inventory(data).issues


def test_string_booleans_are_rejected():
    data = baseline()
    data["execution_authorized"] = "false"
    data["readiness_passed"] = "false"
    issues = assess_inventory(data).issues
    assert "EXECUTION_MUST_BE_FALSE" in issues
    assert "READINESS_MUST_BE_FALSE" in issues


def test_cases_cannot_be_claimed_executed():
    data = baseline()
    data["physical_cases"][0] = "PASS"
    assert "PHYSICAL_CASES_MUST_BE_NOT_RUN" in assess_inventory(data).issues


def test_invalid_and_mixed_type_controls_fail_closed():
    data = baseline()
    data["controls"][42] = {"status": "PASS"}
    assert "UNKNOWN_CONTROL" in assess_inventory(data).issues
    assert assess_inventory(None).status == "BLOCKED"


def test_interactive_allow_requires_absent_deny():
    report = {"launcher": "CreateProcessWithLogonW", "logon_type": "interactive",
              "seclogon_state": "Running"}
    for role in ("collector", "storage"):
        report[role] = dict(account_enabled=True, effective_interactive_allow=True,
                            effective_interactive_deny_absent=True,
                            non_admin=True, acl_isolated=True)
    assert assess_logon(report).status == "BLOCKED"
    report["collector"]["effective_interactive_deny_absent"] = False
    assert "collector:DENY_OVERRIDES_ALLOW_OR_UNKNOWN" in assess_logon(report).issues


def test_batch_right_is_not_interactive_allow():
    report = {"launcher": "CreateProcessWithLogonW", "logon_type": "batch",
              "seclogon_state": "Stopped",
              "collector": {"SeBatchLogonRight": True},
              "storage": {"SeBatchLogonRight": True}}
    issues = assess_logon(report).issues
    assert "INTERACTIVE_LOGON_UNVERIFIED" in issues
    assert "SECLOGON_NOT_CONFIRMED_RUNNING" in issues


def test_missing_logon_report_blocks():
    assert assess_logon(None).status == "BLOCKED"
