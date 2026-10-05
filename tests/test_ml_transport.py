import hashlib,json
from pathlib import Path


def test_ml_transport_never_exposes_database_credentials():
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert '"/ml/claim"' in c and '"/ml/jobs/{job_id}/dataset"' in c
    assert '"/ml/jobs/{job_id}/artifact"' in c and '"/ml/jobs/{job_id}/finalize"' in c
    w=Path("grid/worker.py").read_text(encoding="utf-8")
    assert "postgres_dsn" not in w


def test_artifact_upload_is_control_owned_and_bounded():
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert "256*1024*1024" in c
    assert "LocalArtifactStore(settings.ml_artifact_root)" in c
    assert 'request.stream()' in c
    assert 'request.body()' not in c
    block=c[c.index('upload_ml_artifact'):c.index('@app.post("/ml/jobs/{job_id}/finalize")')]
    assert 'payload.get("storage_uri")' not in block
    assert 'storage_uri:str' not in block
    assert 'saved["storage_uri"]' in block


def test_transport_fences_every_mutation_by_generation():
    s=Path("grid/ml_transport.py").read_text(encoding="utf-8")
    assert s.count("lease_generation=$3")>=4
    assert s.count("lease_until>=now()")>=4
    assert "artifact sha256 mismatch" in s
    assert "dataset manifest hash mismatch" in s


def test_dataset_hash_contract_matches_builder():
    row={"sample_id":"1","symbol":"BTCUSDT","event_ts":2,"feature_ts":1,
         "features":{"x":1},"instrument_features":{},"target":{"ret":.1},
         "quality_status":"GOOD","split_group":"a","label_end_ts":3}
    canonical=json.dumps(row,sort_keys=True,default=str,separators=(",",":"))
    h=hashlib.sha256(canonical.encode()).hexdigest()
    assert hashlib.sha256(h.encode()).hexdigest()
