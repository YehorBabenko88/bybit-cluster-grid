from vm_principal_lab.readiness_audit import audit_readiness_document

def valid():
    return {
        "status": "BLOCKED_UNPROVEN",
        "readiness_passed": False,
        "execution_authorized": False,
        "deployment_authorized": False,
        "cases": {f"VM-NEG-{i:02d}": "NOT_RUN" for i in range(1, 13)},
        "hostile_admin": True,
        "hostile_admin_action": "STOP",
    }

def test_valid_blocked_document():
    assert audit_readiness_document(valid()) == ()

def test_forged_ready_rejected():
    data = valid()
    data["status"] = "READY"
    data["execution_authorized"] = True
    data["readiness"] = "PASS"
    issues = audit_readiness_document(data)
    assert "STATUS_NOT_BLOCKED" in issues
    assert "EXECUTION_AUTHORIZED_NOT_FALSE" in issues
    assert "READINESS_PROMOTION" in issues

def test_missing_and_modified_cases_rejected():
    data = valid()
    del data["cases"]["VM-NEG-12"]
    data["cases"]["VM-NEG-01"] = "PASSED"
    issues = audit_readiness_document(data)
    assert "CASE_SET_MISMATCH" in issues
    assert "VM-NEG-01:NOT_NOT_RUN" in issues

def test_hostile_admin_stop_required():
    data = valid()
    data["hostile_admin_action"] = "CONTINUE"
    assert "HOSTILE_ADMIN_STOP_MISSING" in audit_readiness_document(data)

def test_missing_boolean_cannot_default_to_safe():
    data = valid()
    del data["readiness_passed"]
    assert "READINESS_PASSED_NOT_FALSE" in audit_readiness_document(data)
