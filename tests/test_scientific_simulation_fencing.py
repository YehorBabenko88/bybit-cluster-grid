from pathlib import Path


def test_attempt_fencing_applies_to_all_simulation_status_writes():
    source = Path("grid/scientific_simulation_gate.py").read_text(encoding="utf-8")
    assert "attempt_id=uuid.uuid4()" in source
    assert "attempt_id=$2" in source
    assert "AND attempt_id=$3" in source
    assert "AND attempt_id=$6" in source
    assert "FOR UPDATE" in source
    assert '"SKIPPED_STALE_ATTEMPT"' in source
    waiting = source.split("async def _waiting(", 1)[1].split("async def _fail(", 1)[0]
    failed = source.split("async def _fail(", 1)[1].split("def _dict(", 1)[0]
    assert "AND attempt_id=$3" in waiting
    assert "AND attempt_id=$3" in failed


def test_fencing_migration_exists():
    source = Path("grid/migrations.py").read_text(encoding="utf-8")
    assert '"scientific_simulation_attempt_fencing"' in source
    assert "ADD COLUMN IF NOT EXISTS attempt_id uuid" in source
