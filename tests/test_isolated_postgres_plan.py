import copy
import pytest

from installer.isolated_postgres_plan import ProvisioningBlocked, validate_postgres_plan


def example():
    return {
        "schema": 1,
        "run_id": "a" * 32,
        "node_id": "LAB01",
        "data_root": "C:\\GridLab\\" + "a" * 32 + "\\LAB01\\pgdata",
        "port": 25432,
        "postgres_major": 16,
        "listen_address": "127.0.0.1",
        "existing_cluster": False,
        "runtime_stopped": True,
        "operator_approved": True,
    }


def test_valid_plan_is_never_execution_authorization():
    result = validate_postgres_plan(example())
    assert result["status"] == "VALIDATED_PLAN_ONLY"
    assert result["execution_authorized"] is False
    assert result["physical_ready"] is False
    assert "NO_INITDB_EXECUTOR" in result["blockers"]


@pytest.mark.parametrize("field,value", [
    ("schema", True),
    ("node_id", "LS5"),
    ("node_id", "LS7"),
    ("data_root", "C:\\ProgramData\\BybitClusterGrid\\pgdata"),
    ("data_root", "C:\\GridLab\\..\\production\\pgdata"),
    ("data_root", "\\\\server\\share\\pgdata"),
    ("port", 5432.0),
    ("port", 70000),
    ("postgres_major", 17),
    ("listen_address", "0.0.0.0"),
    ("listen_address", "100.100.100.100"),
    ("existing_cluster", True),
    ("runtime_stopped", False),
    ("operator_approved", False),
])
def test_unsafe_plan_is_rejected(field, value):
    plan = copy.deepcopy(example())
    plan[field] = value
    with pytest.raises(ProvisioningBlocked):
        validate_postgres_plan(plan)


def test_unknown_fields_are_rejected():
    plan = example()
    plan["execute"] = True
    with pytest.raises(ProvisioningBlocked, match="PLAN_SCHEMA_INVALID"):
        validate_postgres_plan(plan)
