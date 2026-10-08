"""Readiness gates prevent confirming a live but nonfunctional release."""
from grid.release_supervisor import _confirm, _after_exit, _ready


class FakeProcess:
    def __init__(self,pid=4242,alive=True):
        self.pid=pid
        self.alive=alive
    def poll(self):
        return None if self.alive else 1


def test_worker_readiness_requires_matching_process(tmp_path):
    marker=tmp_path/"ready"
    proc=FakeProcess()
    assert not _ready("worker",proc,str(marker))
    marker.write_text("999",encoding="ascii")
    assert not _ready("worker",proc,str(marker))
    marker.write_text("4242",encoding="ascii")
    assert _ready("worker",proc,str(marker))


def test_unready_release_is_not_confirmed_after_stable_uptime(tmp_path,monkeypatch):
    root=tmp_path
    (root/"pending.version").write_text("new",encoding="utf-8")
    proc=FakeProcess()
    monkeypatch.setattr("grid.release_supervisor.time.sleep",lambda _:None)
    _confirm(root,"new",proc,60,"worker",str(root/"ready"))
    assert (root/"pending.version").exists()
    (root/"ready").write_text("4242",encoding="ascii")
    _confirm(root,"new",proc,60,"worker",str(root/"ready"))
    assert not (root/"pending.version").exists()


def test_unready_long_lived_release_still_rolls_back(tmp_path):
    root=tmp_path
    releases=root/"releases"
    (releases/"old").mkdir(parents=True)
    (releases/"old"/"run_worker.py").write_text("",encoding="utf-8")
    (root/"current.version").write_text("new",encoding="utf-8")
    (root/"previous.version").write_text("old",encoding="utf-8")
    (root/"pending.version").write_text("new",encoding="utf-8")
    assert not _after_exit(root,"new",3600)
    assert not _after_exit(root,"new",3600)
    assert _after_exit(root,"new",3600)
    assert (root/"current.version").read_text(encoding="utf-8")=="old"
