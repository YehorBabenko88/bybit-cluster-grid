from pathlib import Path

def test_repair_preserves_node_identity():
    text=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    assert 'secrets\\node.credential' in text
    assert 'Existing node credential found; preserving node identity.' in text
    assert 'bootstrap.staging' in text
    assert 'bootstrap.previous' in text

def test_postgres_repair_reuses_owned_instance():
    text=Path("installer/provision_postgres.ps1").read_text(encoding="utf-8")
    assert 'postgres-owned.json' in text
    assert 'Reusing Grid-owned PostgreSQL instance.' in text
    assert 'refusing to rotate credentials automatically' in text
    assert 'Unrelated PostgreSQL exists' in text

def test_install_state_modes_exist():
    text=Path("installer/bootstrap.ps1").read_text(encoding="utf-8")
    for mode in ('"fresh"','"repair"','"upgrade"'):
        assert mode in text
    assert 'install-state.json' in text


def test_worker_install_never_starts_legacy_direct_db_archive_service():
    text=Path("installer/install.ps1").read_text(encoding="utf-8")
    assert 'Unregister-ScheduledTask $ArchiveTaskName' in text
    assert 'Register-ScheduledTask -TaskName $ArchiveTaskName' not in text
    assert 'Start-ScheduledTask $ArchiveTaskName' not in text
