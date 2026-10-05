from pathlib import Path
import time
from grid.maintenance import cleanup_owned_temp_files


def test_control_starts_retention_and_maintenance():
    s=Path("grid/coordinator.py").read_text(encoding="utf-8")
    startup=s.split("async def startup():",1)[1].split('@app.on_event("shutdown")',1)[0]
    assert "retention_scheduler(db.pool,settings)" in startup
    assert "maintenance_scheduler(db.pool,settings)" in startup


def test_temp_cleanup_only_removes_old_owned_temp_files(tmp_path):
    old=tmp_path/"old.part";old.write_text("x")
    fresh=tmp_path/"fresh.tmp";fresh.write_text("x")
    keep=tmp_path/"model.bin";keep.write_text("x")
    age=time.time()-90000
    import os
    os.utime(old,(age,age))
    removed=cleanup_owned_temp_files(tmp_path,older_than_seconds=86400)
    assert removed==1
    assert not old.exists()
    assert fresh.exists()
    assert keep.exists()


def test_maintenance_never_deletes_ready_datasets_or_registered_models():
    s=Path("grid/maintenance.py").read_text(encoding="utf-8")
    assert "d.status IN ('FAILED','BUILDING')" in s
    assert "NOT EXISTS(SELECT 1 FROM model_registry" in s
    assert "DELETE FROM model_registry" not in s
