from pathlib import Path

def test_join_agent_requires_https_bundle_and_sha256():
    s=Path("installer/join-agent.ps1").read_text(encoding="utf-8")
    assert 'ValidatePattern("^https://")' in s
    assert "BundleSha256" in s
    assert "Get-FileHash" in s
    assert "Bundle SHA256 mismatch" in s

def test_join_agent_never_accepts_windows_admin_credentials():
    s=Path("installer/join-agent.ps1").read_text(encoding="utf-8").lower()
    assert "password" not in s
    assert "credential" not in s

def test_control_firewall_is_not_public_internet_wide():
    s=Path("installer/configure-control-firewall.ps1").read_text(encoding="utf-8")
    assert "LocalSubnet,100.64.0.0/10" in s
    assert "-LocalPort 8765" in s

def test_bootstrap_supports_external_verified_bundle_path():
    s=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert '[string]$BundlePath=""' in s
    assert "if($BundlePath)" in s

def test_telegram_can_issue_server_authorized_join_tokens():
    s=Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert 'cmd in ("/joinpilot","/joinagent")' in s
    assert "create_enrollment_token" in s
    assert "timedelta(minutes=15)" in s


def test_bootstrap_applies_control_firewall_and_uninstall_removes_it():
    b=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    u=Path("installer/uninstall.ps1").read_text(encoding="utf-8")
    assert "configure-control-firewall.ps1" in b
    assert 'if($AgentMode -eq "CONTROL")' in b
    assert "BybitClusterGrid Coordinator Management" in u
    assert "Remove-NetFirewallRule" in u


def test_join_agent_cannot_choose_install_role():
    s=Path("installer/join-agent.ps1").read_text(encoding="utf-8")
    assert '[ValidateSet("PILOT","NORMAL")]' not in s
    assert '-AgentMode AUTO' in s

def test_server_returns_authorized_role_and_bootstrap_uses_it():
    coordinator=Path("grid/coordinator.py").read_text(encoding="utf-8")
    enroll=Path("installer/enroll.ps1").read_text(encoding="utf-8")
    bootstrap=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert '"install_mode":install_mode' in coordinator
    assert "install_mode=$r.install_mode" in enroll
    assert '$AgentMode=[string]$Enrollment.install_mode' in bootstrap
    assert "CONTROL authorized node mode" in bootstrap
