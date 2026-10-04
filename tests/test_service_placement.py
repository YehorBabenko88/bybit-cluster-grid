from pathlib import Path


def test_archive_pipeline_is_control_owned():
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    archive_block=s[s.index("# Archive/backfill owns direct PostgreSQL work"):s.index('if($Mode -eq "CONTROL"){',s.index("# Archive/backfill owns direct PostgreSQL work"))+250]
    assert 'if($Mode -eq "CONTROL")' in archive_block
    assert 'Register-ScheduledTask -TaskName $ArchiveTaskName' in archive_block
    assert 'if($Mode -eq "NORMAL")' not in archive_block


def test_control_starts_archive_and_agents_do_not():
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    control=s[s.index('if($Mode -eq "CONTROL"){',s.index("$CoordinatorLauncher")):]
    assert "Start-ScheduledTask $CoordinatorTaskName" in control
    assert "Start-ScheduledTask $ArchiveTaskName" in control
    agent=control[control.index("}else{"):]
    assert "Start-ScheduledTask $TaskName" in agent
    assert "Start-ScheduledTask $ArchiveTaskName" not in agent
