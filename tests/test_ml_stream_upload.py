from pathlib import Path
import hashlib,os
from grid.ml_artifact_store import LocalArtifactStore


def test_streamed_upload_does_not_buffer_request_body():
    s=Path("grid/coordinator.py").read_text(encoding="utf-8")
    block=s.split('async def upload_ml_artifact',1)[1].split('@app.post("/ml/jobs/{job_id}/finalize")',1)[0]
    assert "request.stream()" in block
    assert "request.body()" not in block
    assert "256*1024*1024" in block
    assert "os.fsync" in block
    assert "artifact sha256 mismatch" in block


def test_artifact_store_adopts_owned_temp(tmp_path):
    store=LocalArtifactStore(tmp_path)
    temp=tmp_path/"upload.tmp"
    data=b"abc123";temp.write_bytes(data)
    h=hashlib.sha256(data).hexdigest()
    saved=store.adopt_temp(temp,len(data),h)
    assert not temp.exists()
    assert saved["bytes"]==len(data)
    assert saved["sha256"]==h
    assert store.delete_uri(saved["storage_uri"]) is True
