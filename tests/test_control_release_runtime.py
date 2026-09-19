from pathlib import Path
from grid.update_manager import switch_current, rollback

def test_control_only_release_is_runnable(tmp_path):
    release=tmp_path/"releases"/"2"
    release.mkdir(parents=True)
    (release/"run_coordinator.py").write_text("pass",encoding="utf-8")
    switch_current(tmp_path,"2")
    assert (tmp_path/"current.version").read_text(encoding="utf-8")=="2"

def test_control_rollback_accepts_coordinator_release(tmp_path):
    for version in ("1","2"):
        release=tmp_path/"releases"/version
        release.mkdir(parents=True)
        (release/"run_coordinator.py").write_text("pass",encoding="utf-8")
    switch_current(tmp_path,"2")
    assert rollback(tmp_path)=="1"
    assert (tmp_path/"current.version").read_text(encoding="utf-8")=="1"

def test_coordinator_port_is_consistent():
    py=Path("run_coordinator.py").read_text(encoding="utf-8")
    ps=Path("installer/coordinator-launcher.ps1").read_text(encoding="utf-8")
    assert "port=8765" in py
    assert "--port 8765" in ps
