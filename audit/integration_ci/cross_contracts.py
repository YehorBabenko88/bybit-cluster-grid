"""Pure cross-component contract checks, without importing deployment modules."""

def inspect_contracts(vm, postgres, attestation):
    errors = []
    if not all(isinstance(x, dict) for x in (vm, postgres, attestation)):
        return ["contracts must be objects"]
    for contract, key in ((vm, "ownership_session"), (postgres, "ownership_session"), (attestation, "session")):
        if not isinstance(contract.get(key), str) or not contract[key].strip():
            errors.append("ownership session must be a nonempty string")
    if vm.get("mode") != "PlanOnly":
        errors.append("VM mode must be PlanOnly")
    if vm.get("physical_cases_status") != "NOT_RUN":
        errors.append("physical VM cases must be NOT_RUN")
    if postgres.get("mode") != "read-only":
        errors.append("PostgreSQL adapter must be read-only")
    if postgres.get("schema_version") != 1 or type(postgres.get("schema_version")) is not int:
        errors.append("schema-2 prohibited")
    if postgres.get("ownership_session") != vm.get("ownership_session"):
        errors.append("ownership session mismatch")
    if attestation.get("authenticated") is not True:
        errors.append("attestation must be authenticated")
    if attestation.get("session") != vm.get("ownership_session"):
        errors.append("attestation session mismatch")
    if attestation.get("readiness_passed") is not False:
        errors.append("readiness must remain false")
    if attestation.get("execution_authorized") is not False:
        errors.append("execution must remain unauthorized")
    return errors
