from pathlib import Path

from grid.live_assignment_policy import guarded_live_symbols


ALL_SYMBOLS=[
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
    "ADAUSDT","BNBUSDT","AVAXUSDT",
]

FULL_ASSIGNMENT=[f"SYM{i}USDT" for i in range(890)]


def guarded(market,install,live,assignments=None,instruments=None):
    return guarded_live_symbols(
        market_enabled=market,
        install_mode=install,
        live_mode=live,
        node_assignments=FULL_ASSIGNMENT if assignments is None else assignments,
        instrument_symbols=ALL_SYMBOLS if instruments is None else instruments,
    )


def test_normal_normal_active_receives_full_assignment():
    result=guarded(True,"NORMAL","NORMAL",instruments=set(FULL_ASSIGNMENT))
    assert result == FULL_ASSIGNMENT
    assert len(result) == 890


def test_pilot_validating_active_is_hard_capped_at_five_and_scheduler_owned():
    pilot=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]
    result=guarded(True,"PILOT","PILOT_VALIDATING",assignments=pilot)
    assert result == pilot
    assert len(result) <= 5


def test_pilot_can_never_take_normal_full_assignment():
    assert guarded(True,"PILOT","NORMAL") == []


def test_normal_node_cannot_enter_pilot_assignment_path():
    assert guarded(True,"NORMAL","PILOT_VALIDATING") == []


def test_unknown_install_mode_is_fail_closed():
    assert guarded(True,"UNKNOWN","NORMAL") == []
    assert guarded(True,None,"NORMAL") == []


def test_paused_is_fail_closed_for_every_role():
    assert guarded(True,"PILOT","PAUSED") == []
    assert guarded(True,"NORMAL","PAUSED") == []


def test_inactive_fleet_is_always_empty():
    assert guarded(False,"NORMAL","NORMAL") == []
    assert guarded(False,"PILOT","PILOT_VALIDATING") == []


def test_pilot_only_receives_available_preferred_symbols():
    result=guarded(
        True,
        "PILOT",
        "PILOT_VALIDATING",
        assignments=["BTCUSDT","SOLUSDT","ADAUSDT"],
        instruments={"BTCUSDT","SOLUSDT","ADAUSDT"},
    )
    assert result == ["BTCUSDT","SOLUSDT"]


def test_enrollment_role_is_control_authorized():
    s=Path("grid/enrollment.py").read_text(encoding="utf-8")

    assert "authorized_mode text NOT NULL DEFAULT 'UNKNOWN'" in s
    assert "async def create_enrollment_token(pool, label, expires_at, authorized_mode):" in s
    assert "async def enroll(pool, token, node_id):" in s
    assert 'row["authorized_mode"]' in s
    assert "async def registered_install_mode(pool,node_id):" in s


def test_installer_cannot_transmit_install_mode():
    e=Path("installer/enroll.ps1").read_text(encoding="utf-8")
    b=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")

    assert "$InstallMode" not in e
    body_line=next(line for line in e.splitlines() if "$body=" in line)
    assert "install_mode" not in body_line.lower()
    assert "-InstallMode $AgentMode" not in b
