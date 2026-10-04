from grid import local_operator_gate as g


def test_compute_local_gate_honors_operator_stop_and_pause(tmp_path,monkeypatch):
    monkeypatch.setattr(g,"_root",lambda:tmp_path)
    assert g.compute_locally_enabled() is True
    (tmp_path/"operator.stop").write_text("stopped")
    assert g.compute_locally_enabled() is False
    (tmp_path/"operator.stop").unlink()
    (tmp_path/"bootstrap.pause").write_text("paused")
    assert g.compute_locally_enabled() is False
