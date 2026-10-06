from pathlib import Path


def test_ingest_does_not_require_fleet_shared_token():
    src = Path("grid/coordinator.py").read_text(encoding="utf-8")
    minute = src[src.index('@app.post("/ingest/minute")'):src.index('@app.post("/ingest/event")')]
    event = src[src.index('@app.post("/ingest/event")'):src.index('@app.post("/ml/claim")')]
    for block in (minute, event):
        assert "authenticate_agent(db.pool,x_node_id,x_node_credential)" in block
        assert "constant_time_equal(x_grid_token,settings.grid_shared_token)" not in block


def test_enrollment_persists_node_id():
    src = Path("installer/enroll.ps1").read_text(encoding="utf-8")
    assert '"node.id"' in src
    assert "Set-Content -Path $NodeIdFile -Value $r.node_id" in src


def test_runtime_prefers_persisted_node_id():
    src = Path("grid/resources.py").read_text(encoding="utf-8")
    assert '"secrets","node.id"' in src
    assert "persisted=f.read().strip()" in src
    assert "return persisted" in src
