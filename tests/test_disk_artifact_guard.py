import pytest
from grid.ml_artifact_store import LocalArtifactStore
import grid.disk_guard as dg


def test_local_artifact_store_is_owned_and_idempotent(tmp_path):
    store=LocalArtifactStore(tmp_path)
    row=store.put_bytes(b"model-data")
    assert row["bytes"]==10
    assert row["storage_uri"].startswith("artifact://local/")
    assert store.delete_uri(row["storage_uri"]) is True
    assert store.delete_uri(row["storage_uri"]) is False


def test_local_artifact_store_refuses_foreign_uri(tmp_path):
    store=LocalArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.delete_uri("foreign://artifact")


def test_disk_guard_orders_pressure(monkeypatch,tmp_path):
    class U:
        total=100*1024**3
        free=50*1024**3
    monkeypatch.setattr(dg.shutil,"disk_usage",lambda p:U())
    assert dg.disk_state(tmp_path)["state"]==dg.NORMAL
    U.free=25*1024**3
    assert dg.disk_state(tmp_path)["state"]==dg.SOFT
    U.free=10*1024**3
    assert dg.disk_state(tmp_path)["state"]==dg.HARD
    U.free=2*1024**3
    assert dg.disk_state(tmp_path)["state"]==dg.EMERGENCY
