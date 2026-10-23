"""Offline fail-closed source guards; no native calls or Windows hosts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_admin_group_requires_enabled_and_not_deny_only():
    source = (ROOT / "TokenFacts.cs").read_text(encoding="utf-8")
    assert '(g.Attr & 0x00000004u)!=0' in source
    assert '(g.Attr & 0x00000010u)==0' in source
    assert 'if(Sid(g.Sid)=="S-1-5-32-544") f.admin_group=true;' not in source


def test_cleanup_remains_explicitly_disabled():
    source = (ROOT / "Invoke-Pc4SidAcl.ps1").read_text(encoding="utf-8")
    start = source.index("if($Cleanup){")
    approval = source.index("if(!$ApproveFixtureCleanup)", start)
    assert "throw 'CLEANUP_DISABLED_PENDING_HANDLE_RELATIVE_REVIEW'" in source[start:approval]


def test_actor_shutdown_has_bounded_wait():
    source = (ROOT / "Invoke-Pc4SidAcl.ps1").read_text(encoding="utf-8")
    assert "$processes[$role].WaitForExit(5000)" in source
    assert "Kill(" not in source
