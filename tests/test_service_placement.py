from pathlib import Path


def test_archive_pipeline_is_control_owned():
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    archive_block=s[s.index("# Archive/backfill owns direct PostgreSQL work"):s.index('if($Mode -eq "CONTROL"){',s.index("# Archive/backfill owns direct PostgreSQL work"))+250]
    assert 'if($Mode -eq "CONTROL")' in archive_block
    assert 'Register-ScheduledTask -TaskName $ArchiveTaskName' in archive_block
    assert 'if($Mode -eq "NORMAL")' not in archive_block


def test_control_starts_archive_and_agents_do_not():
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    marker='if($Mode -eq "CONTROL"){'
    # The file has two CONTROL blocks. The second one owns coordinator/agent
    # startup, so anchor after the first archive-placement block.
    first=s.index(marker,s.index("# Archive/backfill owns direct PostgreSQL work"))
    second=s.index(marker,first+len(marker))
    control=s[second:]
    outer_else='''}else{
  Unregister-ScheduledTask $CoordinatorTaskName'''
    split=control.index(outer_else)
    control_branch=control[:split]
    agent_branch=control[split:]
    assert "Start-ScheduledTask $CoordinatorTaskName" in control_branch
    assert "Start-ScheduledTask $ArchiveTaskName" in control_branch
    assert "Start-ScheduledTask $TaskName" in agent_branch
    assert "Start-ScheduledTask $ArchiveTaskName" not in agent_branch
