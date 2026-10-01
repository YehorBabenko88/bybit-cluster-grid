from pathlib import Path

import pytest

from grid.enrollment import (
    AUTHORIZED_INSTALL_MODES,
    _normalize_authorized_mode,
)


def test_only_authorized_modes_exist():
    assert AUTHORIZED_INSTALL_MODES == {"PILOT", "NORMAL"}


def test_mode_normalization():
    assert _normalize_authorized_mode("pilot") == "PILOT"
    assert _normalize_authorized_mode("normal") == "NORMAL"


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        _normalize_authorized_mode("UNKNOWN")


def test_empty_mode_is_rejected():
    with pytest.raises(ValueError):
        _normalize_authorized_mode(None)


def test_enroll_endpoint_does_not_accept_client_role():
    source = Path("grid/coordinator.py").read_text(encoding="utf-8")

    start = source.index('@app.post("/enroll")')
    end = source.index("async def node_auth", start)

    block = source[start:end]

    assert 'payload.get("install_mode")' not in block
    assert 'payload["install_mode"]' not in block


def test_token_schema_contains_authorized_role():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    assert "authorized_mode text NOT NULL DEFAULT 'UNKNOWN'" in source
    assert "SELECT authorized_mode" in source
    assert 'row["authorized_mode"]' in source


def test_installer_never_sends_role():
    enroll = Path("installer/enroll.ps1").read_text(encoding="utf-8")
    bootstrap = Path("installer/bootstrap.ps1").read_text(encoding="utf-8")

    assert "$InstallMode" not in enroll
    assert "install_mode" not in enroll.lower()
    assert "-InstallMode $AgentMode" not in bootstrap

def test_normal_token_has_expansion_gate():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    assert "async def normal_enrollment_allowed(pool):" in source
    assert "mode='READY_FOR_EXPANSION'" in source
    assert "phase='COMPLETE'" in source
    assert "paused=false" in source
    assert 'if authorized_mode == "NORMAL":' in source
    assert "if not await normal_enrollment_allowed(pool):" in source


def test_normal_gate_is_fail_closed():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    assert (
        "NORMAL enrollment is locked until pilot is READY_FOR_EXPANSION"
        in source
    )


def test_pilot_token_does_not_require_expansion_gate():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    start = source.index(
        "async def create_enrollment_token("
    )
    end = source.index(
        "async def enroll(",
        start,
    )

    block = source[start:end]

    assert 'if authorized_mode == "NORMAL":' in block
    assert 'if authorized_mode == "PILOT":' not in block


def test_enrollment_initializes_server_lifecycle_state():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    assert 'if install_mode == "PILOT":' in source
    assert 'lifecycle_mode = "PILOT_BOOTSTRAP"' in source
    assert 'lifecycle_phase = "WAITING"' in source
    assert 'lifecycle_mode = "NORMAL"' in source
    assert 'lifecycle_phase = "COMPLETE"' in source
    assert "INSERT INTO pilot_bootstrap_state" in source


def test_pilot_lifecycle_starts_fail_closed_before_validation():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    assert 'lifecycle_mode = "PILOT_BOOTSTRAP"' in source
    assert 'lifecycle_progress = 0' in source


def test_normal_lifecycle_is_initialized_only_after_authorized_enrollment():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    assert 'lifecycle_mode = "NORMAL"' in source
    assert 'lifecycle_phase = "COMPLETE"' in source
    assert 'lifecycle_progress = 100' in source


def test_credential_and_lifecycle_are_in_same_transaction():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    start = source.index("async def enroll(")
    end = source.index("async def authenticate_agent(", start)
    block = source[start:end]

    transaction = block.index("async with c.transaction():")
    credential = block.index("INSERT INTO agent_credentials")
    lifecycle = block.index("INSERT INTO pilot_bootstrap_state")

    assert transaction < credential < lifecycle


def test_reenrollment_cannot_reset_existing_lifecycle():
    source = Path("grid/enrollment.py").read_text(encoding="utf-8")

    start = source.index("INSERT INTO pilot_bootstrap_state")
    end = source.index("return credential", start)
    block = source[start:end]

    assert "ON CONFLICT(node_id) DO NOTHING" in block
    assert "mode=EXCLUDED.mode" not in block
    assert "phase=EXCLUDED.phase" not in block


def test_reenrollment_cannot_change_existing_server_role():
    source=Path("grid/enrollment.py").read_text(encoding="utf-8")
    assert "existing node role does not match enrollment authorization" in source
    assert "existing_mode != install_mode" in source
    # The mismatch check must happen before token consumption.
    assert source.index("existing_mode != install_mode") < source.index("UPDATE enrollment_tokens SET used_at=now()")
