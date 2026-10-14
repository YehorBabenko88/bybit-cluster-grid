from pathlib import Path


def test_unfenced_archive_pipeline_is_never_registered():
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    # PR178 refuses this standalone writer. The old test positively required
    # starting it; commissioning now requires fail-closed placement for all roles.
    assert 'Register-ScheduledTask -TaskName $ArchiveTaskName' not in s
    assert 'Start-ScheduledTask $ArchiveTaskName' not in s


def test_preparation_never_starts_or_removes_existing_tasks():
    s=Path("installer/install.ps1").read_text(encoding="utf-8")
    assert 'Start-ScheduledTask ' not in s
    assert 'Unregister-ScheduledTask ' not in s
    assert '$Settings.Enabled=$false' in s
    assert s.index('if(!$Apply)') < s.index('New-Item ')
