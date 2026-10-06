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
    assert "100.64.0.0/10" in s
    assert "fd7a:115c:a1e0::/48" in s
    assert "LocalSubnet" not in s
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


def test_auto_onboarding_can_retry_after_partial_failure_with_fresh_token():
    s=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert "existing credential requires repair/upgrade workflow" not in s
    assert "fresh one-time EnrollmentToken" in s


def test_bootstrap_failure_boundary_covers_dependency_and_enrollment_steps():
    s=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    marker=s.index('Write-Host "Grid install mode: $Mode"')
    outer_try=s.index("try {",marker)
    discovery=s.index("$Discovery=",marker)
    pip_install=s.index("-m pip install",marker)
    enrollment=s.index('if($AgentMode -eq "AUTO")',marker)
    common_catch=s.rindex("} catch {")
    assert marker < outer_try < discovery < pip_install < enrollment < common_catch
    assert "--retries 8" in s
    assert 'status="failed"' in s
    assert "Bootstrap rolled back to previous release." in s
