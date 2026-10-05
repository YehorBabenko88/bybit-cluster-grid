from pathlib import Path


def test_agent_does_not_buffer_full_dataset_or_artifact():
    s=Path("grid/ml_agent_worker.py").read_text(encoding="utf-8")
    block=s.split("async def execute_remote_job",1)[1].split("async def ml_agent_loop",1)[0]
    assert "client.dataset(" not in block
    assert "artifact.read_bytes()" not in block
    assert "_write_paged_bundle" in block
    assert "_file_sha256" in block
    assert "artifact_file" in block


def test_dataset_transport_is_paged_and_bounded():
    s=Path("grid/ml_transport.py").read_text(encoding="utf-8")
    assert "async def dataset_page" in s
    assert "min(1000,int(limit))" in s
    c=Path("grid/coordinator.py").read_text(encoding="utf-8")
    assert "offset:int=0,limit:int=500" in c


def test_agent_renews_lease_during_dataset_transfer():
    s=Path("grid/ml_agent_worker.py").read_text(encoding="utf-8")
    block=s.split("async def _write_paged_bundle",1)[1].split("def _file_sha256",1)[0]
    assert "await client.renew(job)" in block
    assert "dataset payload hash mismatch" in block
    assert "dataset hash mismatch" in s
